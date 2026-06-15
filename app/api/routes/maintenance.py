"""维护端点：清空上传缓存等。"""
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.session import APIResponse

router = APIRouter(tags=["maintenance"])

UPLOAD_DIR = Path("uploads")
PROJECT_DIR = Path(__file__).resolve().parent.parent.parent.parent


@router.post("/clear-uploads", response_model=APIResponse)
async def clear_uploads(current_user: User = Depends(get_current_user)):
    """清空 uploads/ 目录中的所有音频文件（不可逆）。

    安全措施：仅删除项目目录内的文件，防止路径遍历攻击。
    """
    abs_upload = UPLOAD_DIR.resolve()
    if not str(abs_upload).startswith(str(PROJECT_DIR)):
        raise HTTPException(status_code=500, detail="上传目录路径异常")

    files = []
    total_size = 0
    if UPLOAD_DIR.exists():
        for f in UPLOAD_DIR.rglob("*"):
            if f.is_file() and str(f.resolve()).startswith(str(PROJECT_DIR)):
                total_size += f.stat().st_size
                files.append(str(f.relative_to(UPLOAD_DIR)))

    if not files:
        return APIResponse(
            code=200,
            message="上传目录已为空，无需清理",
            data={"file_count": 0, "total_size_mb": 0, "deleted_dirs": 0, "errors": []},
        )

    size_mb = round(total_size / 1024 / 1024, 2)
    deleted_count = 0
    errors = []
    for item in list(UPLOAD_DIR.iterdir()):
        try:
            if not str(item.resolve()).startswith(str(PROJECT_DIR)):
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
            deleted_count += 1
        except Exception as e:
            errors.append(str(e))

    msg = f"已清理 {len(files)} 个音频文件，释放 {size_mb} MB 磁盘空间"
    if errors:
        msg += f"（{len(errors)} 个删除失败）"

    return APIResponse(
        code=200,
        message=msg,
        data={
            "file_count": len(files),
            "total_size_mb": size_mb,
            "deleted_dirs": deleted_count,
            "errors": errors,
        },
    )
