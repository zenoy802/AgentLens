from app.models.connection import Connection
from app.models.label import LabelRecord, LabelSchema
from app.models.llm import LLMAnalysis, LLMProvider
from app.models.misc import GlobalRenderRule, QueryHistory
from app.models.named_query import NamedQuery
from app.models.view_config import ViewConfig


def import_all_models() -> None:
    _ = (
        Connection,
        NamedQuery,
        ViewConfig,
        LabelSchema,
        LabelRecord,
        LLMProvider,
        LLMAnalysis,
        GlobalRenderRule,
        QueryHistory,
    )


__all__ = [
    "Connection",
    "GlobalRenderRule",
    "LLMAnalysis",
    "LLMProvider",
    "LabelRecord",
    "LabelSchema",
    "NamedQuery",
    "QueryHistory",
    "ViewConfig",
    "import_all_models",
]

