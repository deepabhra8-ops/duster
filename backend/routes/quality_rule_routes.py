from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from core.config import DQ_RESULTS_MAX_PAGE_SIZE
from engine.quality.models import RuleValidationError
from repositories.dq_rule_repository import DqRuleConflictError
from routes.auth_routes import require_auth
from services.dq_rule_service import DqRulePermissionError, dq_rule_service
from services.dq_run_service import dq_run_service
from utils.logger import get_logger


logger = get_logger(__name__)


quality_rules_bp = APIRouter()


def _error(message: str, status_code: int) -> JSONResponse:
    return JSONResponse({"ok": False, "error": message}, status_code=status_code)


async def _body(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception:
        raise RuleValidationError("Request body must be JSON") from None

    if not isinstance(body, dict):
        raise RuleValidationError("Request body must be a JSON object")

    return body


def _page_args(request: Request, default_size: int, max_size: int) -> tuple[int, int]:
    try:
        page = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("pageSize", default_size))
    except (TypeError, ValueError):
        raise RuleValidationError("page and pageSize must be whole numbers") from None

    if page < 1 or not 1 <= page_size <= max_size:
        raise RuleValidationError(f"page must be at least 1 and pageSize between 1 and {max_size}")

    return page, page_size


# Static paths are declared before /api/quality-rules/{rule_id} so "runs",
# "templates" and "dry-run" are never mistaken for a rule id.


@quality_rules_bp.get("/api/quality-rules/templates")
def list_templates():
    return {"ok": True, "data": dq_rule_service.templates()}


@quality_rules_bp.post("/api/quality-rules/dry-run")
async def dry_run(request: Request):
    try:
        return {"ok": True, "data": dq_run_service.dry_run(await _body(request))}
    except RuleValidationError as exc:
        return _error(str(exc), 400)
    except Exception:
        logger.exception("Data-quality dry run failed")
        return _error("Failed to build the dry-run plan", 500)


@quality_rules_bp.get("/api/quality-rules/runs")
def list_runs(request: Request):
    try:
        page, page_size = _page_args(request, default_size=20, max_size=100)
        return {"ok": True, "data": dq_run_service.list_runs(page, page_size)}
    except RuleValidationError as exc:
        return _error(str(exc), 400)
    except Exception:
        logger.exception("Failed to list data-quality runs")
        return _error("Failed to load runs", 500)


@quality_rules_bp.post("/api/quality-rules/runs")
async def start_run(request: Request, username: str = Depends(require_auth)):
    try:
        run = dq_run_service.start(await _body(request), username)
        return JSONResponse({"ok": True, "data": run}, status_code=202)
    except RuleValidationError as exc:
        return _error(str(exc), 400)
    except Exception:
        logger.exception("Failed to start a data-quality run")
        return _error("Failed to start the run", 500)


@quality_rules_bp.get("/api/quality-rules/runs/{run_id}")
def get_run(run_id: str):
    try:
        summary = dq_run_service.summary(run_id)

        if summary is None:
            return _error("Run not found", 404)

        return {"ok": True, "data": summary}
    except Exception:
        logger.exception("Failed to read data-quality run '%s'", run_id)
        return _error("Failed to load the run", 500)


@quality_rules_bp.get("/api/quality-rules/runs/{run_id}/results")
def get_run_results(run_id: str, request: Request):
    try:
        page, page_size = _page_args(request, default_size=50, max_size=DQ_RESULTS_MAX_PAGE_SIZE)
        status = request.query_params.get("status", "ALL")
        results = dq_run_service.results_page(run_id, status, page, page_size)

        if results is None:
            return _error("Run not found", 404)

        return {"ok": True, "data": results}
    except RuleValidationError as exc:
        return _error(str(exc), 400)
    except Exception:
        logger.exception("Failed to read results for data-quality run '%s'", run_id)
        return _error("Failed to load results", 500)


@quality_rules_bp.get("/api/quality-rules/runs/{run_id}/results.csv")
def download_run_results(run_id: str):
    try:
        exported = dq_run_service.results_csv(run_id)

        if exported is None:
            return _error("Run not found", 404)

        resolved_id, content = exported
        return Response(
            content=content,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="dq-results-{resolved_id}.csv"'},
        )
    except Exception:
        logger.exception("Failed to export results for data-quality run '%s'", run_id)
        return _error("Failed to export results", 500)


@quality_rules_bp.post("/api/quality-rules/runs/{run_id}/cancel")
def cancel_run(run_id: str, username: str = Depends(require_auth)):
    try:
        outcome = dq_run_service.cancel(run_id, username)
    except Exception:
        logger.exception("Failed to cancel data-quality run '%s'", run_id)
        return _error("Failed to cancel the run", 500)

    if outcome == "not_found":
        return _error("Run not found", 404)

    if outcome == "forbidden":
        return _error("Only the person who started the run or an administrator can cancel it", 403)

    if outcome == "not_cancellable":
        return _error("The run has already finished", 409)

    return {"ok": True, "data": {"status": outcome}}


@quality_rules_bp.get("/api/quality-rules")
def list_rules():
    try:
        return {"ok": True, "data": dq_rule_service.library()}
    except Exception:
        logger.exception("Failed to list data-quality rules")
        return _error("Failed to load rules", 500)


@quality_rules_bp.post("/api/quality-rules")
async def create_rule(request: Request, username: str = Depends(require_auth)):
    try:
        rule = dq_rule_service.create(await _body(request), username)
        return JSONResponse({"ok": True, "data": rule}, status_code=201)
    except RuleValidationError as exc:
        return _error(str(exc), 400)
    except DqRuleConflictError as exc:
        return _error(str(exc), 409)
    except Exception:
        logger.exception("Failed to create a data-quality rule")
        return _error("Failed to save the rule", 500)


@quality_rules_bp.get("/api/quality-rules/{rule_id}")
def get_rule(rule_id: str):
    try:
        rule = dq_rule_service.get(rule_id)

        if rule is None:
            return _error("Rule not found", 404)

        return {"ok": True, "data": rule}
    except Exception:
        logger.exception("Failed to read data-quality rule '%s'", rule_id)
        return _error("Failed to load the rule", 500)


@quality_rules_bp.put("/api/quality-rules/{rule_id}")
async def update_rule(rule_id: str, request: Request, username: str = Depends(require_auth)):
    try:
        rule = dq_rule_service.update(rule_id, await _body(request), username)

        if rule is None:
            return _error("Rule not found", 404)

        return {"ok": True, "data": rule}
    except RuleValidationError as exc:
        return _error(str(exc), 400)
    except DqRulePermissionError as exc:
        return _error(str(exc), 403)
    except DqRuleConflictError as exc:
        return _error(str(exc), 409)
    except Exception:
        logger.exception("Failed to update data-quality rule '%s'", rule_id)
        return _error("Failed to save the rule", 500)


@quality_rules_bp.patch("/api/quality-rules/{rule_id}")
async def set_rule_enabled(rule_id: str, request: Request, username: str = Depends(require_auth)):
    try:
        body = await _body(request)
        rule = dq_rule_service.set_enabled(rule_id, body.get("enabled"), username)

        if rule is None:
            return _error("Rule not found", 404)

        return {"ok": True, "data": rule}
    except RuleValidationError as exc:
        return _error(str(exc), 400)
    except DqRulePermissionError as exc:
        return _error(str(exc), 403)
    except Exception:
        logger.exception("Failed to change data-quality rule '%s'", rule_id)
        return _error("Failed to save the rule", 500)


@quality_rules_bp.post("/api/quality-rules/{rule_id}/duplicate")
def duplicate_rule(rule_id: str, username: str = Depends(require_auth)):
    try:
        rule = dq_rule_service.duplicate(rule_id, username)

        if rule is None:
            return _error("Rule not found", 404)

        return JSONResponse({"ok": True, "data": rule}, status_code=201)
    except (RuleValidationError, DqRuleConflictError) as exc:
        return _error(str(exc), 409)
    except Exception:
        logger.exception("Failed to duplicate data-quality rule '%s'", rule_id)
        return _error("Failed to duplicate the rule", 500)


@quality_rules_bp.delete("/api/quality-rules/{rule_id}")
def delete_rule(rule_id: str, username: str = Depends(require_auth)):
    try:
        if not dq_rule_service.delete(rule_id, username):
            return _error("Rule not found", 404)

        return {"ok": True}
    except DqRulePermissionError as exc:
        return _error(str(exc), 403)
    except Exception:
        logger.exception("Failed to delete data-quality rule '%s'", rule_id)
        return _error("Failed to delete the rule", 500)
