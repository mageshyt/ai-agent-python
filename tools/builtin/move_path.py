from pathlib import Path
from typing import Tuple
import shutil

from pydantic import BaseModel, Field

from lib.paths import ensure_parent_directory
from lib import resolve_path
from tools.base import Tool, ToolInvocation, ToolKind, ToolResult


class MovePathParams(BaseModel):
    src: str = Field(..., description="Source file or directory to move (relative to working directory or absolute path)")
    dest: str = Field(..., description="Destination path (file or directory). If an existing directory, source will be moved into it.")
    overwrite: bool = Field(False, description="Whether to overwrite the destination if it exists. If destination is a directory, its existing contents will be removed before moving.")
    create_dirs: bool = Field(True, description="Create destination parent directories if they do not exist.")
    dry_run: bool = Field(False, description="If true, perform validation and report the planned move without changing the filesystem.")


class MovePathTool(Tool):
    name = "move_path"
    description = (
        "Rename or move a file/directory within the workspace. "
        "Honors workspace boundaries, supports dry-run, optional overwrite, and parent directory creation."
    )
    kind = ToolKind.WRITE
    schema = MovePathParams


    async def execute(self,invocation:ToolInvocation)->ToolResult:
        params = MovePathParams(**invocation.params)

        src_path = resolve_path(invocation.cwd,params.src)
        dest_path = resolve_path(invocation.cwd,params.dest)

        cwd = Path(invocation.cwd).resolve()

        def _is_within(base:Path , target: Path)->bool:
            try :
                target.resolve().relative_to(base)
                return True
            except Exception:
                return False


        if not _is_within(cwd,src_path):
            return ToolResult.error_result(
                    f"source Path '{src_path} is outside the workspace '{cwd}' . Move operations are restricted to the workspace"
                    )


        if not  src_path.exists():
            return ToolResult.error_result(f"source path dose not exist : {src_path}")

        # compute final destination: if dest is existing directory, move inside it
        final_dest = self._compute_final_dest(src_path,dest_path)

        # prevent moving a directory into itself or its descendant
        if src_path.is_dir() and self._is_descendant(final_dest , src_path):
            return ToolResult.error_result(
                f"Invalid destination: cannot move a directory '{src_path}' into itself or one of its subdirectories ('{final_dest}')."
            )

        # ensure destination parent is inside workspace
        if not _is_within(cwd,final_dest.parent):
            return ToolResult.error_result(
                f"Destination '{final_dest}' is outside the workspace '{cwd}'. Move operations are restricted to the workspace.")



        if final_dest.exists():
            if not params.overwrite:
                return ToolResult.error_result(
                    f"Destination already exists: {final_dest}. Set 'overwrite' to true to replace it.")


        if params.dry_run:
            return ToolResult.success_result(
                    self._format_plan(src_path,final_dest,params),
                    metadata  = {
                        "source": str(src_path),
                        "destination": str(final_dest),
                        "is_directory": src_path.is_dir(),
                        "action": "plan",
                    }
            )


        if params.create_dirs:
            try:
                ensure_parent_directory(final_dest)
            except Exception as e:
                return ToolResult.error_result(f"Failed to create a destination parent directories : {e}")

        else:
            if not final_dest.parent.exists():
                return ToolResult.error_result(
                    f"Destination parent directory does not exist: {final_dest.parent}")


        if final_dest.exists() and params.overwrite:
            try :
                if final_dest.is_dir():
                    # if final dest is a dir remove all files else remove the file alone
                    shutil.rmtree(final_dest)
                else:
                    final_dest.unlink()
            except Exception as e:
                return ToolResult.error_result(f"Failed to remove existing destination '{final_dest}'")


        # perform move
        try:
            moved_count = self._count_items(src_path)
            shutil.move(str(src_path),str(final_dest))
        except Exception as e:
            return ToolResult.error_result(f"move failed: {e}")

        verb = "directory" if final_dest.is_dir() or src_path.is_dir() else "file"
        note = f"Moved {verb} '{src_path}' -> '{final_dest}'."
        if verb == "directory":
            note += f" Items moved: {moved_count}."

        return ToolResult.success_result(
            note,
            metadata={
                "source": str(src_path),
                "destination": str(final_dest),
                "is_directory": src_path.is_dir(),
                "items_moved": moved_count,
                "action": "moved",
            },
        )
    
    def _compute_final_dest(self,src_path:Path,dest_path:Path)->Path:
        """If destination exists and is a directory, move into it; otherwise use as final path."""
        if dest_path.exists() and dest_path.is_dir():
            return dest_path / src_path.name
        return dest_path


    def _is_descendant(self,target:Path,base:Path)->bool:
        try:
            target.resolve().relative_to(base.resolve())
            return True
        except Exception:
            return False


    

    def _count_items(self, src_path: Path) -> int:
        if src_path.is_file():
            return 1
        count = 0
        for _ in src_path.rglob('*'):
            count += 1
        # include the directory root itself
        return count + 1

    def _format_plan(self, src_path: Path, final_dest: Path, params: MovePathParams) -> str:
        kind = "directory" if src_path.is_dir() else "file"
        plan = [
                f"Would move {kind}:",
                f"  from: {src_path}",
                f"  to:   {final_dest}",
                f"  overwrite: {params.overwrite}",

            f"  create_dirs: {params.create_dirs}",
        ]
        return "\n".join(plan)

if __name__ == "__main__":
    import asyncio
    from config.config import Config

    async def main():
        tool = MovePathTool(Config())
        # Example dry-run usage
        result = await tool.execute(
            ToolInvocation(cwd=Path.cwd(), params={
                "src": "README.md",
                "dest": "tmp/README_moved.md",
                "overwrite": False,
                "create_dirs": True,
                "dry_run": True,
            })
        )
        print(result.to_model_output())

    asyncio.run(main())

