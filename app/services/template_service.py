from app.models.template import TemplateDocument
from app.repositories.template_repository import TemplateRepository
from app.schemas.template import TemplateResponse


class TemplateService:
    def __init__(self, templates: TemplateRepository) -> None:
        self._templates = templates

    async def list_templates(self) -> list[TemplateResponse]:
        templates = await self._templates.list_all()
        return [self._to_response(template) for template in templates]

    def _to_response(self, template: TemplateDocument) -> TemplateResponse:
        return TemplateResponse.model_validate(
            {
                **template.model_dump(),
                "id": template.id,
            }
        )
