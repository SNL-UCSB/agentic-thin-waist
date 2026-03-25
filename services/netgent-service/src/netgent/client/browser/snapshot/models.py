from __future__ import annotations

import base64
import json
import struct
from collections.abc import Iterable
from io import BytesIO

from PIL import Image, ImageDraw, ImageFile, ImageFont
from pydantic import BaseModel, ConfigDict, Field


class BrowserCDPBox(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2

    def translated(self, *, dx: float = 0.0, dy: float = 0.0) -> BrowserCDPBox:
        return BrowserCDPBox(
            x=self.x + dx,
            y=self.y + dy,
            width=self.width,
            height=self.height,
        )

    def point_at(
        self, *, x_ratio: float = 0.5, y_ratio: float = 0.5
    ) -> tuple[float, float]:
        return (
            self.x + self.width * x_ratio,
            self.y + self.height * y_ratio,
        )

    def intersects(self, other: BrowserCDPBox) -> bool:
        return (
            self.x < other.right
            and self.right > other.x
            and self.y < other.bottom
            and self.bottom > other.y
        )


class BrowserCDPSnapshotNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str
    role: str
    backend_node_id: int | None = None
    name: str | None = None
    value: str | None = None
    checked: bool | None = None
    disabled: bool | None = None
    expanded: bool | None = None
    bounds: BrowserCDPBox | None = None
    children: tuple["BrowserCDPSnapshotNode", ...] = ()

    def iter_nodes(self) -> Iterable["BrowserCDPSnapshotNode"]:
        yield self
        for child in self.children:
            yield from child.iter_nodes()

    def render_lines(self, depth: int = 0) -> list[str]:
        indent = "  " * depth
        line = f"{indent}- {self.role}"
        if self.name:
            line += f" {json.dumps(self.name)}"

        details = [f"ref={self.ref}"]
        if self.value:
            details.append(f"value={json.dumps(self.value)}")
        if self.checked is not None:
            details.append(f"checked={str(self.checked).lower()}")
        if self.disabled:
            details.append("disabled=true")
        if self.expanded is not None:
            details.append(f"expanded={str(self.expanded).lower()}")
        if self.bounds is not None:
            details.append(
                "bounds="
                + json.dumps(
                    {
                        "x": round(self.bounds.x, 2),
                        "y": round(self.bounds.y, 2),
                        "width": round(self.bounds.width, 2),
                        "height": round(self.bounds.height, 2),
                    }
                )
            )
        line += f" [{' '.join(details)}]"

        lines = [line]
        for child in self.children:
            lines.extend(child.render_lines(depth + 1))
        return lines


BrowserCDPSnapshotNode.model_rebuild()


class BrowserCDPSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selector: str
    url: str
    title: str
    generated_at: str | None = None
    root: BrowserCDPSnapshotNode | None = None
    refs: dict[str, BrowserCDPSnapshotNode] = Field(default_factory=dict)

    @classmethod
    def from_root(
        cls,
        *,
        selector: str,
        url: str,
        title: str,
        generated_at: str | None,
        root: BrowserCDPSnapshotNode | None,
    ) -> BrowserCDPSnapshot:
        refs = {node.ref: node for node in root.iter_nodes()} if root else {}
        return cls(
            selector=selector,
            url=url,
            title=title,
            generated_at=generated_at,
            root=root,
            refs=refs,
        )

    @property
    def markdown(self) -> str:
        if self.root is None:
            return ""
        return "\n".join(self.root.render_lines())

    def node_for_ref(self, ref: str) -> BrowserCDPSnapshotNode | None:
        return self.refs.get(ref)


class BrowserCDPAnnotation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str
    label: str
    role: str
    name: str | None = None
    bounds: BrowserCDPBox


class BrowserCDPScreenshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selector: str
    url: str
    title: str
    generated_at: str | None = None
    mime_type: str = "image/png"
    image_base64: str
    width: int
    height: int
    full_page: bool = False
    snapshot: BrowserCDPSnapshot | None = None
    annotations: tuple[BrowserCDPAnnotation, ...] = ()

    @property
    def image_bytes(self) -> bytes:
        return base64.b64decode(self.image_base64)

    @property
    def data_url(self) -> str:
        return f"data:{self.mime_type};base64,{self.image_base64}"

    @property
    def annotated_image_bytes(self) -> bytes:
        image, image_draw, font = _load_annotation_canvas(self.image_bytes)
        palette = (
            "#d7263d",
            "#f46036",
            "#2e294e",
            "#1b998b",
            "#c5d86d",
            "#33658a",
            "#86bbd8",
            "#f6ae2d",
        )

        for index, annotation in enumerate(self.annotations):
            color = palette[index % len(palette)]
            box = annotation.bounds
            image_draw.rounded_rectangle(
                (box.x, box.y, box.x + box.width, box.y + box.height),
                radius=8,
                outline=color,
                width=3,
            )

            label_text = annotation.label
            text_bbox = image_draw.textbbox((0, 0), label_text, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
            badge_width = max(28, text_width + 14)
            badge_height = max(20, text_height + 10)
            badge_x = box.x
            badge_y = max(2.0, box.y - badge_height - 6)
            image_draw.rounded_rectangle(
                (badge_x, badge_y, badge_x + badge_width, badge_y + badge_height),
                radius=6,
                fill=color,
            )
            image_draw.text(
                (
                    badge_x + (badge_width - text_width) / 2,
                    badge_y + (badge_height - text_height) / 2 - text_bbox[1],
                ),
                label_text,
                font=font,
                fill="#ffffff",
            )

        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    @property
    def annotated_image_base64(self) -> str:
        return base64.b64encode(self.annotated_image_bytes).decode("ascii")

    @property
    def annotated_svg(self) -> str:
        return (
            "annotated_svg is no longer the primary overlay output; "
            "use annotated_image_bytes or annotated_image_base64 instead."
        )

    @classmethod
    def from_image_base64(
        cls,
        *,
        selector: str,
        url: str,
        title: str,
        generated_at: str | None,
        image_base64: str,
        full_page: bool,
        snapshot: BrowserCDPSnapshot | None,
        annotations: tuple[BrowserCDPAnnotation, ...],
    ) -> BrowserCDPScreenshot:
        image_bytes = base64.b64decode(image_base64)
        width, height = _read_png_size(image_bytes)
        return cls(
            selector=selector,
            url=url,
            title=title,
            generated_at=generated_at,
            image_base64=image_base64,
            width=width,
            height=height,
            full_page=full_page,
            snapshot=snapshot,
            annotations=annotations,
        )


def _read_png_size(image_bytes: bytes) -> tuple[int, int]:
    if image_bytes[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Expected a PNG image from Page.captureScreenshot")
    if len(image_bytes) < 24:
        raise ValueError("Incomplete PNG payload returned from Page.captureScreenshot")
    return struct.unpack(">II", image_bytes[16:24])


def _load_annotation_canvas(image_bytes: bytes):
    ImageFile.LOAD_TRUNCATED_IMAGES = True
    image = Image.open(BytesIO(image_bytes)).convert("RGBA")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 14)
    except OSError:
        font = ImageFont.load_default()
    return image, draw, font
