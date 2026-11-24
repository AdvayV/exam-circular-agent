"""Schedule data shared by extraction and calendar comparison."""

from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class Exam(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    course_code: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9-]*$", max_length=40)
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    source_page: int = Field(ge=1)
    source_text: str = Field(min_length=1, max_length=250)

    @model_validator(mode="after")
    def check_times(self) -> Self:
        if self.ends_at <= self.starts_at:
            raise ValueError("An exam must end after it starts.")
        return self


class Schedule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    status: Literal["applicable", "not_applicable", "needs_review"]
    programme: str = Field(min_length=1)
    term: str = Field(min_length=1)
    exams: tuple[Exam, ...]
    notes: tuple[str, ...]

    @model_validator(mode="after")
    def check_applicability(self) -> Self:
        if self.status != "applicable" and self.exams:
            raise ValueError("Only applicable schedules can contain proposed exam dates.")
        return self
