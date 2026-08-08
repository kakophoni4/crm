from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modules.db.models.base import Base
from app.modules.db.models.uploaded_file import UploadedFile


class DepartmentTaskFile(Base):
    __tablename__ = "department_task_files"
    __table_args__ = (
        UniqueConstraint("task_id", "file_id", name="uq_department_task_files_task_file"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("department_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("uploaded_files.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    file: Mapped[UploadedFile] = relationship(lazy="selectin")
