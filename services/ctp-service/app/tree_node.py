"""
tree_node.py — Network subnet tree node.

Defines the ``TreeNode`` data structure used to represent aggregated traffic
statistics for an IPv4 subnet.  Each node stores download/upload fragment
time-series and computes derived metrics (burstiness, throughput, asymmetry,
median).  Nodes are arranged in a hierarchy from /32 leaf nodes (individual
users) up to a single /0 root.
"""
from __future__ import annotations

import ipaddress

import numpy as np

from time_series_modules import Fragment


class Configuration:
    """Global tunables shared across all ``TreeNode`` computations.

    Attributes:
        PERCENTILE: Percentile used for burstiness calculations.
            A value of 95 means the 95th-percentile byte count is used as
            the peak measurement.
    """

    PERCENTILE = 95


class TreeNode:
    """A node in the hierarchical subnet traffic tree.

    Each ``TreeNode`` corresponds to an IPv4 network (e.g. ``169.231.0.0/16``)
    and holds aggregated download/upload time-series fragments for that subnet.
    Children are the immediate sub-networks one prefix-length smaller.

    Attributes:
        network: The IPv4 network this node represents.
        download_fragment: 100 ms-binned byte counts for inbound traffic.
        upload_fragment: 100 ms-binned byte counts for outbound traffic.
        children: Direct child ``TreeNode`` objects (sub-subnets).
        uplink_burstiness: P95-to-mean ratio for upload traffic.
        downlink_burstiness: P95-to-mean ratio for download traffic.
        total_burstiness: P95-to-mean ratio for combined traffic.
        uplink_bytes: Total upload bytes in the fragment window.
        downlink_bytes: Total download bytes in the fragment window.
        total_bytes: Sum of uplink and downlink bytes.
        asymmetry: Ratio of uplink to downlink bytes (-1 if downlink is 0).
        num_users: Number of /32 leaf nodes under this subnet.
        fwd_packets: Total forward (upload) packet count.
        bwd_packets: Total backward (download) packet count.
        parent: Parent ``TreeNode``, or ``None`` for the root.
        total_median: Median of combined per-bin byte counts.
        downlink_median: Median of download per-bin byte counts.
        uplink_median: Median of upload per-bin byte counts.
    """

    def __init__(
        self,
        network: ipaddress.IPv4Network,
        download_fragment: Fragment,
        upload_fragment: Fragment,
        children: list[TreeNode] | None = None,
    ):
        """Initialise a ``TreeNode`` with its network and traffic fragments.

        Args:
            network: The IPv4 network this node represents.
            download_fragment: Time-series fragment for inbound (download) bytes.
            upload_fragment: Time-series fragment for outbound (upload) bytes.
            children: Pre-existing child nodes.  Defaults to an empty list.
        """
        if children is None:
            children = []
        self.network = network
        self.download_fragment = download_fragment
        self.upload_fragment = upload_fragment
        self.children = children

        # Burstiness
        self.uplink_burstiness: float = 0
        self.downlink_burstiness: float = 0
        self.total_burstiness: float = 0

        # Throughput
        self.uplink_bytes: int = 0
        self.downlink_bytes: int = 0
        self.total_bytes: int = 0

        # Misc
        self.asymmetry: float = -1
        self.num_users: int = 0

        self.bwd_packets = 0
        self.fwd_packets = 0

        self.parent = None

        self.total_median = 0
        self.downlink_median = 0
        self.uplink_median = 0

    def __repr__(self) -> str:
        """Return a concise string showing child networks."""
        return f"Network{[ch.network for ch in self.children]}, {self.children}"

    # ------------------------------------------------------------------
    # Metric computation
    # ------------------------------------------------------------------

    def compute_new_burstiness_measure(self) -> None:
        """Compute per-bin burstiness indicator arrays.

        A bin is flagged as *bursty* (value 1) when either:
        - its byte count is at least twice the fragment mean, or
        - the absolute change from the previous bin is at least twice the mean.

        Populates:
            download_burstiness_measure: Binary array for download traffic.
            upload_burstiness_measure: Binary array for upload traffic.
            total_burstiness_measure: Binary array for combined traffic.
        """
        total_fragment = self.download_fragment.container + self.upload_fragment.container

        download_mean_bytes = np.mean(self.download_fragment.container)
        upload_mean_bytes = np.mean(self.upload_fragment.container)
        total_mean_bytes = np.mean(total_fragment)

        self.download_burstiness_measure = np.full_like(self.download_fragment.container, 0)
        self.upload_burstiness_measure = np.full_like(self.upload_fragment.container, 0)
        self.total_burstiness_measure = np.full_like(self.download_fragment.container, 0)

        for i in range(1, len(self.download_fragment.container)):
            if self.download_fragment.container[i] >= 2 * download_mean_bytes or abs(
                self.download_fragment.container[i - 1] - self.download_fragment.container[i]
            ) >= 2 * download_mean_bytes:
                self.download_burstiness_measure[i] = 1

            if self.upload_fragment.container[i] >= 2 * upload_mean_bytes or abs(
                self.upload_fragment.container[i - 1] - self.upload_fragment.container[i]
            ) >= 2 * upload_mean_bytes:
                self.upload_burstiness_measure[i] = 1

            if total_fragment[i] >= 2 * total_mean_bytes or abs(
                total_fragment[i - 1] - total_fragment[i]
            ) >= 2 * total_mean_bytes:
                self.total_burstiness_measure[i] = 1

    def compute_burstiness(self) -> None:
        """Compute P95-to-mean burstiness ratios for upload, download, and total.

        Burstiness is defined as the ``Configuration.PERCENTILE``-th percentile
        divided by the mean of the traffic array.  A ratio of 1.0 means the
        traffic is perfectly uniform; higher values indicate spikier traffic.

        Skips computation if the mean is zero (no traffic in the window).

        Populates:
            uplink_burstiness, downlink_burstiness, total_burstiness.
        """
        uplink_mean_throughput = np.mean(self.upload_fragment.container)
        downlink_mean_throughput = np.mean(self.download_fragment.container)

        if uplink_mean_throughput != 0:
            self.uplink_burstiness = (
                np.percentile(self.upload_fragment.container, Configuration.PERCENTILE)
                / uplink_mean_throughput
            )
        if downlink_mean_throughput != 0:
            self.downlink_burstiness = (
                np.percentile(self.download_fragment.container, Configuration.PERCENTILE)
                / downlink_mean_throughput
            )

        total_container = self.upload_fragment.container + self.download_fragment.container
        total_mean_throughput = np.mean(total_container)

        if total_mean_throughput != 0:
            self.total_burstiness = (
                np.percentile(total_container, Configuration.PERCENTILE) / total_mean_throughput
            )

    def compute_throughput(self) -> None:
        """Compute total byte counts from the traffic fragments.

        Populates:
            uplink_bytes, downlink_bytes, total_bytes.
        """
        self.uplink_bytes = np.sum(self.upload_fragment.container)
        self.downlink_bytes = np.sum(self.download_fragment.container)
        self.total_bytes = self.uplink_bytes + self.downlink_bytes

    def compute_median(self) -> None:
        """Compute median per-bin byte counts for upload, download, and total.

        Populates:
            uplink_median, downlink_median, total_median.
        """
        self.uplink_median = np.median(self.upload_fragment.container)
        self.downlink_median = np.median(self.download_fragment.container)
        self.total_median = np.median(
            self.download_fragment.container + self.upload_fragment.container
        )

    def compute_asymmetry(self) -> None:
        """Compute the upload-to-download byte ratio.

        Asymmetry values greater than 1 indicate more upload than download
        traffic.  The attribute is left at ``-1`` if ``downlink_bytes`` is
        zero to signal missing data rather than a division-by-zero error.

        Populates:
            asymmetry.
        """
        if self.downlink_bytes != 0:
            self.asymmetry = self.uplink_bytes / self.downlink_bytes

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_parameters(
        cls,
        network: ipaddress.IPv4Network,
        download_fragment: Fragment,
        upload_fragment: Fragment,
        fwd_packets: int,
        bwd_packets: int,
        children: list[TreeNode] | None = None,
    ) -> TreeNode:
        """Create a fully initialised ``TreeNode`` and compute all metrics.

        This is the preferred constructor when building the tree from raw
        fragment data, as it immediately computes burstiness, throughput,
        asymmetry, and median.

        Args:
            network: The IPv4 network this node represents.
            download_fragment: Inbound traffic time-series.
            upload_fragment: Outbound traffic time-series.
            fwd_packets: Total forward (upload) packet count.
            bwd_packets: Total backward (download) packet count.
            children: Pre-existing child nodes.  Defaults to ``None``.

        Returns:
            A ``TreeNode`` with all metrics populated.
        """
        tree_node = cls(network, download_fragment, upload_fragment, children)
        tree_node.fwd_packets = fwd_packets
        tree_node.bwd_packets = bwd_packets
        tree_node.compute_burstiness()
        tree_node.compute_throughput()
        tree_node.compute_asymmetry()
        tree_node.compute_new_burstiness_measure()
        tree_node.compute_median()
        return tree_node

    def add_child(self, child: TreeNode) -> None:
        """Attach *child* as a sub-network of this node.

        Also sets ``child.parent`` to ``self``.

        Args:
            child: The child ``TreeNode`` to attach.
        """
        self.children.append(child)
        child.parent = self

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialise the node and its entire subtree to a plain dictionary.

        The returned structure is JSON-serialisable.  Children are serialised
        recursively.

        Returns:
            A dictionary representation of this node and all descendants.
        """
        return {
            "network": str(self.network),
            "uplink_burstiness": self.uplink_burstiness,
            "downlink_burstiness": self.downlink_burstiness,
            "total_burstiness": self.total_burstiness,
            "uplink_bytes": self.uplink_bytes,
            "downlink_bytes": self.downlink_bytes,
            "total_bytes": self.total_bytes,
            "asymmetry": self.asymmetry,
            "num_users": self.num_users,
            "total_median": self.total_median,
            "downlink_median": self.downlink_median,
            "uplink_median": self.uplink_median,
            "download_fragment": self.download_fragment.container.tolist(),
            "upload_fragment": self.upload_fragment.container.tolist(),
            "children": [child.to_dict() for child in self.children],
        }

    @staticmethod
    def from_json(data: dict) -> TreeNode:
        """Deserialise a single node (no children) from a dictionary.

        This is a low-level helper used by :meth:`from_dict`.  It does not
        recurse into children.

        Args:
            data: A dictionary produced by :meth:`to_dict` (or equivalent).

        Returns:
            A ``TreeNode`` with all scalar attributes restored but an empty
            ``children`` list.
        """
        network = ipaddress.ip_network(data["network"])
        node = TreeNode(
            network,
            Fragment.from_list(data["download_fragment"]),
            Fragment.from_list(data["upload_fragment"]),
        )
        node.total_bytes = data["total_bytes"]
        node.uplink_bytes = data["uplink_bytes"]
        node.downlink_bytes = data["downlink_bytes"]
        node.uplink_burstiness = data["uplink_burstiness"]
        node.downlink_burstiness = data["downlink_burstiness"]
        node.total_burstiness = data["total_burstiness"]
        node.asymmetry = data["asymmetry"]
        node.num_users = data["num_users"]
        node.total_median = data["total_median"]
        node.downlink_median = data["downlink_median"]
        node.uplink_median = data["uplink_median"]
        return node

    @staticmethod
    def from_dict(data: dict) -> TreeNode:
        """Deserialise a full subtree from a dictionary recursively.

        Args:
            data: A dictionary produced by :meth:`to_dict`.

        Returns:
            The root ``TreeNode`` of the reconstructed subtree.
        """
        node = TreeNode.from_json(data)
        for child_data in data["children"]:
            node.add_child(TreeNode.from_dict(child_data))
        return node

    # ------------------------------------------------------------------
    # Traversal utilities
    # ------------------------------------------------------------------

    def print_tree(self, level: int = 0) -> None:
        """Pretty-print the tree structure to stdout.

        Args:
            level: Current indentation depth (used for recursion).
        """
        indent = "  " * level
        if self.children:
            print(f"{indent}{self.network} -> [")
            for child in self.children:
                child.print_tree(level + 1)
            print(f"{indent}]")
        else:
            print(f"{indent}{self.network})")

    def find_subnet(self, target_subnet) -> TreeNode | None:
        """Search the subtree for a node whose network matches *target_subnet*.

        Args:
            target_subnet: An ``IPv4Network`` or any value accepted by
                ``ipaddress.ip_network()``.

        Returns:
            The matching ``TreeNode``, or ``None`` if not found.
        """
        target_subnet = ipaddress.ip_network(target_subnet)
        if self.network == target_subnet:
            return self
        for child in self.children:
            found = child.find_subnet(target_subnet)
            if found:
                return found
        return None

    @staticmethod
    def get_leaf_nodes(root: TreeNode) -> list[TreeNode]:
        """Collect all leaf nodes (nodes with no children) under *root*.

        Uses depth-first search with a visited set to guard against cycles.

        Args:
            root: The ``TreeNode`` at which to start the traversal.

        Returns:
            A list of all leaf ``TreeNode`` objects in DFS order.
        """
        output: list[TreeNode] = []
        visited: set = set()

        def _dfs(node: TreeNode) -> None:
            if node.network in visited:
                return
            visited.add(node.network)
            if not node.children:
                output.append(node)
            for child in node.children:
                _dfs(child)

        _dfs(root)
        return output
