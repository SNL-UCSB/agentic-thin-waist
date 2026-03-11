"""
trees.py — Subnet tree construction and I/O.

This module builds a hierarchical ``TreeNode`` tree from per-user
``TimeSeries`` pickles and serialises each time-slice to JSON.  It also
provides utilities for loading trees back from disk and recomputing derived
statistics.

Pipeline stage: **timeseries → trees**

High-level flow
~~~~~~~~~~~~~~~
1. :func:`filter_users` — discover user IP directories.
2. :func:`extract_time_series` — load ``TimeSeries`` pickles into memory.
3. :func:`construct_trees` — for each time slice *t*:

   a. Create per-user leaf ``TreeNode`` objects from ``download_fragments[t]``
      and ``upload_fragments[t]``.
   b. Iteratively group leaf nodes by progressively shorter prefixes (/31 → /16).
   c. Aggregate fragment arrays at each level to produce parent nodes.
   d. Wrap everything under a single ``0.0.0.0/0`` root.
   e. Save the root to ``<output>/<tree_nodes_t_min.json>``.

4. :func:`post_process_trees` — reload raw trees and recompute medians.
"""
from __future__ import annotations

import ipaddress
import json
import multiprocessing as mp
import os
import pickle
from collections import defaultdict

import numpy as np

from time_series_modules import Fragment, TimeSeries
from tree_node import TreeNode


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def save_tree_to_json(tree: TreeNode, output_file: str) -> None:
    """Serialise a ``TreeNode`` tree to a JSON file.

    The entire subtree rooted at *tree* is serialised via :meth:`TreeNode.to_dict`
    and written with 2-space indentation for readability.

    Args:
        tree: Root node of the tree to serialise.
        output_file: Destination file path.
    """
    with open(output_file, "w") as f:
        json.dump(tree.to_dict(), f, indent=2)
    print(f"Saved Tree - {output_file}")


def load_tree_from_json(input_file: str) -> TreeNode:
    """Deserialise a ``TreeNode`` tree from a JSON file.

    Args:
        input_file: Path to a JSON file written by :func:`save_tree_to_json`.

    Returns:
        The root ``TreeNode`` of the reconstructed tree.
    """
    with open(input_file, "r") as f:
        return TreeNode.from_dict(json.load(f))


# ---------------------------------------------------------------------------
# User discovery
# ---------------------------------------------------------------------------

def filter_users(mask: str, path: str) -> list[ipaddress.IPv4Network]:
    """Return ``IPv4Network`` objects for each user directory matching *mask*.

    Only sub-directories of *path* whose name begins with *mask* are included.
    Pass an empty string to include all user directories.

    Args:
        mask: IP prefix string used to filter user directories, e.g. ``'169.231'``.
            Pass ``''`` to return all users.
        path: Root directory containing one sub-directory per user IP address.

    Returns:
        A list of ``IPv4Network`` objects, one per matching user directory.
    """
    return [
        ipaddress.IPv4Network(name)
        for name in os.listdir(path)
        if os.path.isdir(os.path.join(path, name)) and name.startswith(mask)
    ]


# ---------------------------------------------------------------------------
# Time-series loading
# ---------------------------------------------------------------------------

def extract_time_series(
    user_ips: list[ipaddress.IPv4Network],
    directory: str,
) -> dict[str, TimeSeries]:
    """Load per-user ``TimeSeries`` pickles into a dictionary.

    Expects each user's pickle to be at
    ``<directory>/<ip_address>/timeseries.pkl``.

    Args:
        user_ips: List of user networks returned by :func:`filter_users`.
        directory: Root directory containing per-user time-series sub-directories.

    Returns:
        A mapping from IP address string (e.g. ``'169.231.10.5'``) to the
        corresponding ``TimeSeries`` object.

    Raises:
        FileNotFoundError: If a ``timeseries.pkl`` file is missing for any user.
    """
    time_series_dict: dict[str, TimeSeries] = {}
    for user_ip in user_ips:
        address = str(user_ip.network_address)
        path = os.path.join(directory, address, "timeseries.pkl")
        with open(path, "rb") as f:
            time_series_dict[address] = pickle.load(f)
    return time_series_dict


# ---------------------------------------------------------------------------
# Tree construction — internal helpers
# ---------------------------------------------------------------------------

def _create_user_tree_nodes(
    user_ips: list[ipaddress.IPv4Network],
    time_series_dict: dict[str, TimeSeries],
    time: int,
) -> list[TreeNode]:
    """Build leaf ``TreeNode`` objects for every user at time slice *time*.

    If a user has fewer time-slice fragments than *time* (e.g. their PCAP was
    shorter than the others), an empty ``Fragment`` is substituted so the tree
    has a consistent shape.

    Args:
        user_ips: User networks to build leaf nodes for.
        time_series_dict: Loaded time-series data keyed by IP string.
        time: Zero-based index of the 60-second window to extract.

    Returns:
        One ``TreeNode`` per user, with metrics computed via
        :meth:`TreeNode.from_parameters`.
    """
    tree_node_list: list[TreeNode] = []
    for user_ip in user_ips:
        address = str(user_ip.network_address)
        ts = time_series_dict[address]

        df = (
            Fragment()
            if not ts.download_fragments or len(ts.download_fragments) - 1 < time
            else ts.download_fragments[time]
        )
        uf = (
            Fragment()
            if not ts.upload_fragments or len(ts.upload_fragments) - 1 < time
            else ts.upload_fragments[time]
        )

        tree_node = TreeNode.from_parameters(
            user_ip, df, uf, ts.total_fwd_packets, ts.total_bwd_packets
        )
        tree_node_list.append(tree_node)
    return tree_node_list


def _group_by_upper_subnet(
    tree_nodes: list[TreeNode],
    new_prefix: int,
) -> dict[ipaddress.IPv4Network, list[TreeNode]]:
    """Group ``TreeNode`` objects by their parent subnet at *new_prefix* length.

    Args:
        tree_nodes: Nodes at the current prefix level.
        new_prefix: The shorter prefix length to group by (e.g. 30 groups /31 nodes).

    Returns:
        A ``defaultdict`` mapping each parent subnet to its child ``TreeNode`` list.
    """
    groups: dict[ipaddress.IPv4Network, list[TreeNode]] = defaultdict(list)
    for tree_node in tree_nodes:
        upper_subnet = ipaddress.ip_network(tree_node.network).supernet(new_prefix=new_prefix)
        groups[upper_subnet].append(tree_node)
    return groups


def _convert_to_tree_nodes(
    groups: dict[ipaddress.IPv4Network, list[TreeNode]],
) -> list[TreeNode]:
    """Aggregate grouped child nodes into parent ``TreeNode`` objects.

    For each subnet group, fragment arrays are element-wise summed across all
    children to produce the parent's combined traffic representation.

    Args:
        groups: Mapping from parent subnet to its list of child ``TreeNode`` objects.

    Returns:
        One parent ``TreeNode`` per group, with children attached and metrics
        recomputed from the aggregated fragments.
    """
    new_tree_nodes: list[TreeNode] = []
    for key, value in groups.items():
        download_fragment = Fragment()
        upload_fragment = Fragment()
        df = download_fragment.container
        uf = upload_fragment.container
        fwd_packets = 0
        bwd_packets = 0

        for node in value:
            df = np.add(df, node.download_fragment.container)
            uf = np.add(uf, node.upload_fragment.container)
            fwd_packets += node.fwd_packets
            bwd_packets += node.bwd_packets

        download_fragment.container = df
        upload_fragment.container = uf
        new_tree_nodes.append(
            TreeNode.from_parameters(
                key, download_fragment, upload_fragment, fwd_packets, bwd_packets, value
            )
        )
    return new_tree_nodes


def _calculate_users(root: TreeNode) -> int:
    """Recursively count and store the number of leaf users under *root*.

    Sets ``root.num_users`` to the total leaf count for every internal node
    in the subtree.

    Args:
        root: The subtree root whose user count should be computed.

    Returns:
        The number of leaf nodes (individual users) under *root*.
    """
    if not root.children:
        return 1
    for child in root.children:
        root.num_users += _calculate_users(child)
    return root.num_users


def _recompute_medians(root: TreeNode, visited: set | None = None) -> None:
    """DFS traversal to recompute median metrics on all nodes in the subtree.

    This is called after loading a tree from disk to ensure median values are
    consistent with the stored fragment arrays.

    Args:
        root: The subtree root at which to begin the traversal.
        visited: Set of already-visited networks (used to guard against cycles).
            Pass ``None`` to initialise a fresh set.
    """
    if visited is None:
        visited = set()
    if root.network in visited:
        return
    visited.add(root.network)
    root.compute_median()
    for child in root.children:
        _recompute_medians(child, visited)


# ---------------------------------------------------------------------------
# Public tree construction API
# ---------------------------------------------------------------------------

def construct_trees(
    user_ips: list[ipaddress.IPv4Network],
    time_series_dict: dict[str, TimeSeries],
    segmented_tree_folder: str,
    t: int,
) -> None:
    """Build and save the aggregated subnet tree for time slice *t*.

    Constructs leaf nodes from each user's *t*-th fragment, then iteratively
    aggregates them from /31 up to /16, and finally wraps everything under a
    ``0.0.0.0/0`` root.  The result is written to
    ``<segmented_tree_folder>/tree_nodes_<t>_min.json``.

    Args:
        user_ips: List of user networks (leaf nodes).
        time_series_dict: Pre-loaded ``TimeSeries`` data for all users.
        segmented_tree_folder: Directory to write the output JSON file.
        t: Zero-based time-slice index.
    """
    print(f"Constructing Tree for time slice: {t}")
    prefix = 31

    tree_nodes = _create_user_tree_nodes(user_ips, time_series_dict, t)

    for i in range(prefix, 15, -1):
        groups = _group_by_upper_subnet(tree_nodes, i)
        tree_nodes = _convert_to_tree_nodes(groups)

    root_network = ipaddress.ip_network("0.0.0.0/0")
    tree_nodes = _convert_to_tree_nodes({root_network: tree_nodes})

    if len(tree_nodes) == 1:
        _calculate_users(tree_nodes[0])
        path = os.path.join(segmented_tree_folder, f"tree_nodes_{t}_min.json")
        save_tree_to_json(tree_nodes[0], path)
    else:
        print("Did not allocate tree nodes properly")


def post_process_trees(input_dir: str, output_dir: str, time_limit: int) -> None:
    """Reload raw trees, recompute medians, and re-save to *output_dir*.

    This stage ensures median values are current after loading trees produced
    by an earlier pipeline run.

    Args:
        input_dir: Directory containing ``tree_nodes_<t>_min.json`` files.
        output_dir: Destination directory for post-processed ``tree_nodes_<t>.json`` files.
        time_limit: Number of time slices to process (0 to *time_limit* - 1).
    """
    os.makedirs(output_dir, exist_ok=True)
    for t in range(time_limit):
        input_path = os.path.join(input_dir, f"tree_nodes_{t}_min.json")
        output_path = os.path.join(output_dir, f"tree_nodes_{t}.json")
        root = load_tree_from_json(input_path)
        _recompute_medians(root)
        save_tree_to_json(root, output_path)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build CTP subnet trees.")
    parser.add_argument("--directory", required=True, help="Path to per-user timeseries directories.")
    parser.add_argument("--output", required=True, help="Directory to write tree JSON files.")
    parser.add_argument("--mask", default="", help="IP prefix filter, e.g. '169.231'.")
    parser.add_argument("--time-limit", type=int, default=15, help="Number of time slices.")
    parser.add_argument("--workers", type=int, default=mp.cpu_count(), help="Worker process count.")
    args = parser.parse_args()

    user_ips = filter_users(args.mask, args.directory)
    time_series_dict = extract_time_series(user_ips, args.directory)
    os.makedirs(args.output, exist_ok=True)

    task_args = [
        (user_ips, time_series_dict, args.output, t) for t in range(args.time_limit)
    ]
    with mp.Pool(processes=args.workers) as pool:
        pool.starmap(construct_trees, task_args)

    print("Processing complete for all time slices.")
