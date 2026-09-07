"""GitHub Copilot: .github/copilot-instructions.md and .github/instructions/*."""

from __future__ import annotations

from ..discovery import Workspace, read_text, split_frontmatter, walk_files
from ..models import ALWAYS, CONDITIONAL, Asset


class CopilotAdapter:
    name = "copilot"
    label = "GitHub Copilot"

    def detect(self, ws: Workspace) -> bool:
        return any(
            (r / ".github" / "copilot-instructions.md").is_file()
            or (r / ".github" / "instructions").is_dir()
            or (r / ".github" / "prompts").is_dir()
            for r in ws.roots()
        )

    def collect(self, ws: Workspace) -> list[Asset]:
        out: list[Asset] = []
        for root in ws.roots():
            gh = root / ".github"
            main = gh / "copilot-instructions.md"
            if main.is_file():
                out.append(
                    Asset(
                        assistant=self.name, kind="instruction", name="copilot-instructions.md",
                        loading=ALWAYS, path=main, always_on_text=read_text(main),
                        meta={"scope": ws.scope_of(main)},
                    )
                )
            for f in walk_files(gh / "instructions", "*.instructions.md", max_depth=3):
                fm, body = split_frontmatter(read_text(f))
                apply_to = str(fm.get("applyTo") or "").strip()
                # applyTo "**" is Copilot's way of saying "every file", i.e. always-on.
                always = apply_to in ("**", "**/*", "*")
                out.append(
                    Asset(
                        assistant=self.name, kind="instruction",
                        name=f.name.replace(".instructions.md", ""),
                        loading=ALWAYS if always else CONDITIONAL, path=f,
                        always_on_text=body if always else "",
                        on_demand_text="" if always else body,
                        meta={"scope": ws.scope_of(f), "apply_to": apply_to,
                              "missing_apply_to": not apply_to},
                    )
                )
            for f in walk_files(gh / "prompts", "*.prompt.md", max_depth=3):
                _, body = split_frontmatter(read_text(f))
                out.append(
                    Asset(
                        assistant=self.name, kind="prompt",
                        name=f.name.replace(".prompt.md", ""),
                        loading=CONDITIONAL, path=f, on_demand_text=body,
                        meta={"scope": ws.scope_of(f)},
                    )
                )
        return out
