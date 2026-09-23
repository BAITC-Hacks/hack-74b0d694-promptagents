from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .catalog import Catalog, CatalogError, load_catalog, options
from .config import CONTRACT_VERSION, DEFAULT_DATA_PATH, configured_path
from .models import (
    DataIssue, ErrorDetail, ErrorResponse, HealthResponse, OptionsResponse,
    RecommendRequest, RecommendResponse,
)


def error_response(status: int, code: str, message: str, issues=()) -> JSONResponse:
    body = ErrorResponse(error=ErrorDetail(code=code, message=message, issues=list(issues)))
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"))


def create_app(data_path: Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.catalog = None
        app.state.catalog_error = None
        try:
            app.state.catalog = load_catalog(data_path or configured_path(
                "DATA_PATH", DEFAULT_DATA_PATH,
            ))
        except CatalogError as exc:
            app.state.catalog_error = exc
        yield

    app = FastAPI(title="PromptAgents API", version=CONTRACT_VERSION, lifespan=lifespan)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError):
        return error_response(422, "validation_error", "Проверьте параметры запроса", [
            DataIssue(field=".".join(map(str, item["loc"])), message=item["msg"])
            for item in exc.errors()
        ])

    @app.exception_handler(CatalogError)
    async def data_error(_request: Request, exc: CatalogError):
        return error_response(503, exc.code, "Каталог недоступен. Требуется исправить данные.", exc.issues)

    def get_catalog() -> Catalog:
        if app.state.catalog_error:
            raise app.state.catalog_error
        return app.state.catalog

    @app.get("/api/health", response_model=HealthResponse)
    def health():
        catalog = app.state.catalog
        error = app.state.catalog_error
        return HealthResponse(
            status="ok" if catalog else "degraded", contract_version=CONTRACT_VERSION,
            dataset_status="ready" if catalog else ("missing" if error.code == "dataset_missing" else "invalid"),
            profile_count=len(catalog.profiles) if catalog else 0,
            data_version=catalog.data_version if catalog else None,
            recommendation_implemented=False, issues=error.issues if error else [],
        )

    @app.get("/api/options", response_model=OptionsResponse, responses={503: {"model": ErrorResponse}})
    def get_options():
        return options(get_catalog())

    @app.post("/api/recommend", response_model=RecommendResponse, responses={
        422: {"model": ErrorResponse}, 503: {"model": ErrorResponse}, 501: {"model": ErrorResponse},
    })
    def recommend(request: RecommendRequest):
        get_catalog()
        return error_response(501, "not_implemented", "Подбор ещё не реализован. Это каркас приложения.")

    return app


app = create_app()
