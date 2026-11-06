"""Studio entrypoint for LangGraph Studio visual inspection and execution."""

from app.core.config import settings
from app.graph.nodes import FactoryNodes
from app.graph.workflow import compile_factory_graph
from app.services.llm_gateway import GeminiLLMGateway, MockLLMGateway
from app.services.mail_service import MailService
from app.services.notion_mcp_service import get_knowledge_sync_adapter
from app.services.office_store import OfficeStore
from app.services.prompt_loader import PromptLoader
from app.services.workspace_writer import WorkspaceWriter

prompt_loader = PromptLoader()
workspace_writer = WorkspaceWriter()
office_store = OfficeStore()
mail_service = MailService(office_store)
llm_gateway = MockLLMGateway() if settings.USE_MOCK_LLM else GeminiLLMGateway()
knowledge_sync = get_knowledge_sync_adapter() if settings.NOTION_MCP_ENABLED else None

nodes = FactoryNodes(
    llm_gateway=llm_gateway,
    prompt_loader=prompt_loader,
    workspace_writer=workspace_writer,
    office_store=office_store,
    mail_service=mail_service,
    knowledge_sync=knowledge_sync,
)

# Compile without internal checkpointer as LangGraph Server / Studio injects its own checkpointer
graph = compile_factory_graph(nodes=nodes, checkpointer=None, full_13_agents=True)
