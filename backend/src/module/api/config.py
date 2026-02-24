import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from module.conf import settings
from module.models import APIResponse, Config
from module.security.api import UNAUTHORIZED, get_current_user

router = APIRouter(prefix="/config", tags=["config"])
logger = logging.getLogger(__name__)

_SENSITIVE_KEYS = ("password", "api_key", "token", "secret")


def _sanitize_dict(d: dict) -> dict:
    """Recursively mask string values whose keys contain sensitive keywords."""
    result = {}
    for k, v in d.items():
        if isinstance(v, dict):
            result[k] = _sanitize_dict(v)
        elif isinstance(v, str) and any(s in k.lower() for s in _SENSITIVE_KEYS):
            result[k] = "********"
        else:
            result[k] = v
    return result


@router.get("/get", dependencies=[Depends(get_current_user)])
async def get_config():
    """Return the current configuration with sensitive fields masked."""
    return _sanitize_dict(settings.dict())


@router.patch(
    "/update", response_model=APIResponse, dependencies=[Depends(get_current_user)]
)
async def update_config(config: Config):
    """Persist and reload configuration from the supplied payload."""
    try:
        settings.save(config_dict=config.dict())
        settings.load()
        # update_rss()
        logger.info("Config updated")
        return JSONResponse(
            status_code=200,
            content={
                "msg_en": "Update config successfully.",
                "msg_zh": "更新配置成功。",
            },
        )
    except Exception as e:
        logger.warning(e)
        return JSONResponse(
            status_code=406,
            content={"msg_en": "Update config failed.", "msg_zh": "更新配置失败。"},
        )
