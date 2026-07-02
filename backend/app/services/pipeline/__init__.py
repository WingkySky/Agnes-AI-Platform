# =====================================================
# 流水线服务模块
# 提供创意流水线的模板管理、执行引擎、进度推送等功能
# =====================================================

from app.services.pipeline.engine import (
    PipelineEngine,
    create_pipeline_run,
    start_pipeline,
    resume_pipeline,
    cancel_pipeline,
)
from app.services.pipeline.template_service import (
    get_template_by_id,
    get_template_by_key,
    list_templates,
    create_template,
    update_template,
    delete_template,
    validate_steps_config,
)
from app.services.pipeline.template_validate import (
    get_sample_template,
    validate_template,
    infer_output_mapping,
)
from app.services.pipeline.run_service import (
    get_run_by_id,
    get_run_steps,
    list_runs,
    create_and_start_run,
    retry_run,
    retry_step,
    cancel_run,
    delete_run,
    pause_run,
    update_run_inputs,
    export_run_to_canvas,
    estimate_credits,
    save_subtitles,
)
from app.services.pipeline.sse_manager import pipeline_sse_manager
from app.services.pipeline.integration import (
    save_generation_from_step,
    save_batch_generations,
    estimate_pipeline_total_credits,
    auto_moderate_pipeline_outputs,
)
from app.services.pipeline.post_process_service import post_process_video

__all__ = [
    "PipelineEngine",
    "create_pipeline_run",
    "start_pipeline",
    "resume_pipeline",
    "cancel_pipeline",
    "get_template_by_id",
    "get_template_by_key",
    "list_templates",
    "create_template",
    "update_template",
    "delete_template",
    "validate_steps_config",
    "get_sample_template",
    "validate_template",
    "infer_output_mapping",
    "get_run_by_id",
    "get_run_steps",
    "list_runs",
    "create_and_start_run",
    "retry_run",
    "retry_step",
    "cancel_run",
    "delete_run",
    "pause_run",
    "update_run_inputs",
    "export_run_to_canvas",
    "estimate_credits",
    "save_subtitles",
    "pipeline_sse_manager",
    "save_generation_from_step",
    "save_batch_generations",
    "estimate_pipeline_total_credits",
    "auto_moderate_pipeline_outputs",
    "post_process_video",
]
