from io import BytesIO

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings
from app.models.knowledge import KnowledgeChunkDocument, KnowledgeDocument
from app.models.user import UserDocument
from app.repositories.agent_repository import AgentRepository
from app.repositories.knowledge_repository import KnowledgeRepository


class KnowledgeService:
    def __init__(self, knowledge: KnowledgeRepository, agents: AgentRepository) -> None:
        self._knowledge = knowledge
        self._agents = agents

    async def list_knowledge(self, agent_id: str, user: UserDocument) -> list[KnowledgeDocument]:
        await self._ensure_agent(agent_id, user)
        return await self._knowledge.list_by_agent(user.id or "", agent_id)

    async def upload_knowledge(
        self,
        agent_id: str,
        user: UserDocument,
        file: UploadFile,
    ) -> KnowledgeDocument:
        await self._ensure_agent(agent_id, user)
        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Knowledge file is empty",
            )

        upload_result = self._upload_to_cloudinary(file.filename or "knowledge-file", file_bytes)
        text = self._extract_text(file.filename or "", file.content_type, file_bytes)
        chunks = self._split_text(text)
        embeddings = await self._embed_chunks(chunks)

        knowledge = await self._knowledge.create(
            KnowledgeDocument(
                user_id=user.id or "",
                agent_id=agent_id,
                filename=file.filename or "knowledge-file",
                content_type=file.content_type,
                cloudinary_url=upload_result["secure_url"],
                cloudinary_public_id=upload_result.get("public_id"),
                chunk_count=len(chunks),
            )
        )

        await self._knowledge.create_chunks(
            [
                KnowledgeChunkDocument(
                    knowledge_id=knowledge.id or "",
                    agent_id=agent_id,
                    user_id=user.id or "",
                    chunk_index=index,
                    content=chunk,
                    embedding=embeddings[index],
                )
                for index, chunk in enumerate(chunks)
            ]
        )

        return knowledge

    async def _ensure_agent(self, agent_id: str, user: UserDocument) -> None:
        agent = await self._agents.get_owned(agent_id, user.id or "")
        if agent is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    def _upload_to_cloudinary(self, filename: str, file_bytes: bytes) -> dict:
        if not all(
            [
                settings.cloudinary_cloud_name,
                settings.cloudinary_api_key,
                settings.cloudinary_api_secret,
            ]
        ):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Cloudinary credentials are not configured",
            )

        try:
            import cloudinary
            import cloudinary.uploader
        except ImportError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Cloudinary SDK is not installed. Run pip install -r requirements.txt.",
            ) from exc

        cloudinary.config(
            cloud_name=settings.cloudinary_cloud_name,
            api_key=settings.cloudinary_api_key,
            api_secret=settings.cloudinary_api_secret,
            secure=True,
        )
        return cloudinary.uploader.upload(
            BytesIO(file_bytes),
            folder=settings.cloudinary_folder,
            public_id=filename.rsplit(".", 1)[0],
            resource_type="raw",
            overwrite=True,
        )

    def _extract_text(self, filename: str, content_type: str | None, file_bytes: bytes) -> str:
        if content_type == "application/pdf" or filename.lower().endswith(".pdf"):
            try:
                from pypdf import PdfReader
            except ImportError as exc:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="pypdf is not installed. Run pip install -r requirements.txt.",
                ) from exc

            reader = PdfReader(BytesIO(file_bytes))
            text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
        else:
            text = file_bytes.decode("utf-8", errors="ignore").strip()

        if not text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not extract text from knowledge file",
            )
        return text

    def _split_text(self, text: str) -> list[str]:
        try:
            from langchain_text_splitters import RecursiveCharacterTextSplitter
        except ImportError:
            return [text[index : index + 1200] for index in range(0, len(text), 900)]

        splitter = RecursiveCharacterTextSplitter(chunk_size=1200, chunk_overlap=200)
        return splitter.split_text(text)

    async def _embed_chunks(self, chunks: list[str]) -> list[list[float]]:
        if not settings.openai_api_key:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OPENAI_API_KEY is not configured",
            )

        try:
            from langchain_openai import OpenAIEmbeddings
        except ImportError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="LangChain OpenAI package is not installed. Run pip install -r requirements.txt.",
            ) from exc

        embeddings = OpenAIEmbeddings(
            model=settings.openai_embedding_model,
            api_key=settings.openai_api_key,
        )
        return await embeddings.aembed_documents(chunks)
