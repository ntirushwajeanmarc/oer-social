from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=120)
    cadre: str = "Anesthesia trainee"
    site: str = "Training site"
    education_level: str = Field(default="", max_length=120)
    experience_years: int = Field(default=0, ge=0, le=70)
    learning_goals: str = Field(default="", max_length=2000)
    topics_of_interest: str = Field(default="", max_length=1000)
    preferred_language: str = Field(default="English", max_length=80)
    local_context: str = Field(default="", max_length=2000)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    role: str
    cadre: str
    site: str
    education_level: str
    experience_years: int
    learning_goals: str
    topics_of_interest: str
    preferred_language: str
    local_context: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class GeneratePackRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=800)
    focus: str = Field(
        default="",
        max_length=400,
        description="Optional focus within the topic, e.g. causes, management, reflection",
    )


class QuestionOut(BaseModel):
    id: str
    prompt: str
    question_type: str
    rubric: str
    sort_order: int

    model_config = {"from_attributes": True}


class PackOut(BaseModel):
    id: str
    status: str
    topic: str
    poster_title: str
    poster_caption: str
    poster_visual_prompt: str
    poster_image_path: str = ""
    elaboration: str
    case_study: str
    created_at: datetime
    published_at: datetime | None
    questions: list[QuestionOut] = []

    model_config = {"from_attributes": True}


class PackListItem(BaseModel):
    id: str
    status: str
    topic: str
    poster_title: str
    poster_image_path: str = ""
    created_at: datetime
    published_at: datetime | None
    question_count: int = 0


class AnswerRequest(BaseModel):
    answer: str = Field(min_length=1)


class SubmissionOut(BaseModel):
    id: str
    question_id: str
    answer: str
    score: float
    feedback: str
    created_at: datetime

    model_config = {"from_attributes": True}


class SocialExportOut(BaseModel):
    id: str
    pack_id: str
    platform: str
    status: str
    caption: str
    visual_prompt: str
    poster_title: str
    poster_image_path: str = ""
    external_id: str = ""
    error_message: str = ""
    created_at: datetime


class ProgramBriefUpdate(BaseModel):
    program_topic: str = Field(min_length=3, max_length=4000)
    target_learners: str = Field(min_length=3, max_length=4000)
    oer_rationale: str = Field(min_length=3, max_length=4000)
    distribution_channels: str = Field(min_length=3, max_length=4000)
    learning_objectives: str = Field(min_length=3, max_length=6000)
    approved_references: str = Field(default="", max_length=6000)
    local_context: str = Field(default="", max_length=4000)
    preferred_language: str = Field(default="English", max_length=80)
    restricted_topics: str = Field(default="", max_length=4000)
    brand_tone: str = Field(default="", max_length=2000)
    responsible_educator: str = Field(default="", max_length=200)


class ProgramBriefOut(ProgramBriefUpdate):
    id: str
    version: int
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AiProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)


class AiProjectOut(BaseModel):
    id: str
    name: str
    description: str
    source_project_id: str | None = None
    import_count: int = 0
    chat_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AiChatCreate(BaseModel):
    mode: str = Field(default="work", pattern="^(work|personal)$")
    project_id: str | None = None
    title: str = Field(default="", max_length=500)


class ContinueImportRequest(BaseModel):
    mode: str = Field(default="work", pattern="^(work|personal)$")
    project_id: str | None = None


class AiMessageOut(BaseModel):
    id: str
    role: str
    content: str
    image_path: str = ""
    created_at: datetime

    model_config = {"from_attributes": True}


class AiChatOut(BaseModel):
    id: str
    project_id: str | None
    title: str
    mode: str
    created_at: datetime
    updated_at: datetime
    messages: list[AiMessageOut] = []

    model_config = {"from_attributes": True}


class AiChatListItem(BaseModel):
    id: str
    project_id: str | None
    title: str
    mode: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AiChatUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=500)


class AiMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=12000)
    make_feed: bool = False


class AiMessageUpdate(BaseModel):
    content: str = Field(min_length=1, max_length=12000)
    regenerate: bool = True


class AiImageCreate(BaseModel):
    prompt: str = Field(min_length=3, max_length=4000)
    make_feed: bool = False
    style: str = Field(
        default="poster",
        pattern="^(poster|general)$",
        description="poster = clinical education poster; general = freer image",
    )


class AiMessageResponse(BaseModel):
    message: AiMessageOut
    draft_pack_id: str | None = None
    chat: AiChatOut | None = None


class MessageToFeedRequest(BaseModel):
    publish: bool = False


class MessageToFeedResponse(BaseModel):
    pack_id: str
    status: str
    poster_title: str = ""


class HistoryItem(BaseModel):
    id: str
    title: str
    source: str  # platform | import
    mode: str | None = None
    updated_at: datetime | None = None
    preview: str = ""
    project_id: str | None = None
    project_name: str | None = None


class ImportConversationOut(BaseModel):
    id: str
    title: str
    source_filename: str
    user_text: str
    project_id: str | None = None
    project_name: str | None = None
    conversation_created_at: datetime | None
    conversation_updated_at: datetime | None
    imported_at: datetime

    model_config = {"from_attributes": True}
