"""Lightweight heading-based Markdown block parser.

Splits a Markdown document into sequential blocks at heading boundaries.
Each block tracks its heading text, level, position index, and byte offsets.
"""

from dataclasses import dataclass


@dataclass
class ParsedBlock:
    heading: str
    level: int
    position: int
    start_offset: int
    end_offset: int
    content: str


def parse_blocks(raw_markdown: str) -> list[ParsedBlock]:
    lines = raw_markdown.splitlines(keepends=True)
    blocks: list[ParsedBlock] = []
    current_heading = ""
    current_level = 0
    current_content: list[str] = []
    block_start = 0
    cursor = 0

    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("#"):
            if current_heading or current_content:
                content = "".join(current_content).strip("\n")
                blocks.append(
                    ParsedBlock(
                        heading=current_heading,
                        level=current_level,
                        position=len(blocks),
                        start_offset=block_start,
                        end_offset=cursor,
                        content=content,
                    )
                )
            marker = stripped.split(" ", 1)[0]
            current_level = len(marker)
            current_heading = stripped[len(marker) :].strip()
            current_content = []
            block_start = cursor
        else:
            current_content.append(line)
        cursor += len(line)

    if current_heading or current_content:
        content = "".join(current_content).strip("\n")
        blocks.append(
            ParsedBlock(
                heading=current_heading,
                level=current_level,
                position=len(blocks),
                start_offset=block_start,
                end_offset=cursor,
                content=content,
            )
        )

    return blocks
