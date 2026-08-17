from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="learner")  # admin | learner
    cadre: Mapped[str] = mapped_column(String(80), default="Anesthesia trainee")
    site: Mapped[str] = mapped_column(String(120), default="Training site")
    education_level: Mapped[str] = mapped_column(String(120), default="")
    experience_years: Mapped[int] = mapped_column(Integer, default=0)
    learning_goals: Mapped[str] = mapped_column(Text, default="")
    topics_of_interest: Mapped[str] = mapped_column(Text, default="")
    preferred_language: Mapped[str] = mapped_column(String(80), default="English")
    local_context: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    packs: Mapped[list[ContentPack]] = relationship(back_populates="author")
    submissions: Mapped[list[Submission]] = relationship(back_populates="user")


class ContentPack(Base):
    __tablename__ = "content_packs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    author_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | published
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    poster_title: Mapped[str] = mapped_column(String(240), nullable=False)
    poster_caption: Mapped[str] = mapped_column(Text, nullable=False)
    poster_visual_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    poster_image_path: Mapped[str] = mapped_column(String(500), default="")
    elaboration: Mapped[str] = mapped_column(Text, nullable=False)
    case_study: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    author: Mapped[User] = relationship(back_populates="packs")
    questions: Mapped[list[Question]] = relationship(back_populates="pack", cascade="all, delete-orphan")
    social_posts: Mapped[list[SocialPost]] = relationship(back_populates="pack", cascade="all, delete-orphan")


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    pack_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("content_packs.id"), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[str] = mapped_column(String(40), default="short_answer")
    rubric: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    pack: Mapped[ContentPack] = relationship(back_populates="questions")
    submissions: Mapped[list[Submission]] = relationship(back_populates="question", cascade="all, delete-orphan")


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    question_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("questions.id"), nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    feedback: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="submissions")
    question: Mapped[Question] = relationship(back_populates="submissions")


class SocialPost(Base):
    __tablename__ = "social_posts"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    pack_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("content_packs.id"), nullable=False)
    platform: Mapped[str] = mapped_column(String(40), nullable=False)  # instagram | x | export
    status: Mapped[str] = mapped_column(String(40), default="ready_to_export")
    caption: Mapped[str] = mapped_column(Text, nullable=False)
    external_id: Mapped[str] = mapped_column(String(120), default="")
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    pack: Mapped[ContentPack] = relationship(back_populates="social_posts")


class AdminMemoryConversation(Base):
    __tablename__ = "admin_memory_conversations"
    __table_args__ = (
        UniqueConstraint(
            "admin_id",
            "source_conversation_id",
            name="uq_admin_memory_source_conversation",
        ),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    admin_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id"), nullable=False, index=True
    )
    source_conversation_id: Mapped[str] = mapped_column(String(120), nullable=False)
    source_filename: Mapped[str] = mapped_column(String(500), default="")
    title: Mapped[str] = mapped_column(String(500), default="")
    user_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_project_id: Mapped[str] = mapped_column(String(120), default="", index=True)
    project_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("ai_projects.id"), nullable=True, index=True
    )
    conversation_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    conversation_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    chunks: Mapped[list[AdminMemoryChunk]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class AdminMemoryChunk(Base):
    """Embedded snippets of imported ChatGPT history for vector recall."""

    __tablename__ = "admin_memory_chunks"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "chunk_index",
            name="uq_admin_memory_chunk_conversation_index",
        ),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    conversation_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("admin_memory_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    admin_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    conversation: Mapped[AdminMemoryConversation] = relationship(back_populates="chunks")


class ProgramBrief(Base):
    __tablename__ = "program_briefs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    program_topic: Mapped[str] = mapped_column(Text, nullable=False)
    target_learners: Mapped[str] = mapped_column(Text, nullable=False)
    oer_rationale: Mapped[str] = mapped_column(Text, nullable=False)
    distribution_channels: Mapped[str] = mapped_column(Text, nullable=False)
    learning_objectives: Mapped[str] = mapped_column(Text, nullable=False)
    approved_references: Mapped[str] = mapped_column(Text, default="")
    local_context: Mapped[str] = mapped_column(Text, default="")
    preferred_language: Mapped[str] = mapped_column(String(80), default="English")
    restricted_topics: Mapped[str] = mapped_column(Text, default="")
    brand_tone: Mapped[str] = mapped_column(Text, default="")
    responsible_educator: Mapped[str] = mapped_column(String(200), default="")
    edited_by_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AiProject(Base):
    __tablename__ = "ai_projects"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    admin_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    source_project_id: Mapped[str] = mapped_column(String(120), default="", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    chats: Mapped[list[AiChat]] = relationship(back_populates="project")


class AiChat(Base):
    __tablename__ = "ai_chats"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    admin_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id"), nullable=False, index=True
    )
    project_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("ai_projects.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(500), default="New chat")
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="work")  # work | personal
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    project: Mapped[AiProject | None] = relationship(back_populates="chats")
    messages: Mapped[list[AiMessage]] = relationship(
        back_populates="chat", cascade="all, delete-orphan"
    )


class AiMessage(Base):
    __tablename__ = "ai_messages"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    chat_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("ai_chats.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user | assistant | system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    image_path: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    chat: Mapped[AiChat] = relationship(back_populates="messages")
