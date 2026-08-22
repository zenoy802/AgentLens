from app.models.annotation import Annotation
from app.models.connection import Connection
from app.models.label import LabelRecord, LabelSchema
from app.models.llm import LLMAnalysis, LLMProvider
from app.models.misc import GlobalRenderRule, QueryHistory
from app.models.named_query import NamedQuery
from app.models.selection_snapshot import SelectionSnapshot
from app.models.trace_contract import RunSnapshot, TraceContract
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
        Annotation,
        SelectionSnapshot,
        TraceContract,
        RunSnapshot,
    )


__all__ = [
    "Annotation",
    "Connection",
    "GlobalRenderRule",
    "LLMAnalysis",
    "LLMProvider",
    "LabelRecord",
    "LabelSchema",
    "NamedQuery",
    "QueryHistory",
    "RunSnapshot",
    "SelectionSnapshot",
    "TraceContract",
    "ViewConfig",
    "import_all_models",
]
