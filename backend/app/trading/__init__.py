"""Trading layer built on top of the Renko engine."""

__all__ = [
    "LivePipelineReport",
    "LivePipelineResult",
    "LiveRuntimeOrchestrator",
    "LiveTradingPipeline",
    "RuntimeHealth",
]


def __getattr__(name: str):
    if name in {"LivePipelineReport", "LivePipelineResult", "LiveTradingPipeline"}:
        from backend.app.trading.live_pipeline import LivePipelineReport, LivePipelineResult, LiveTradingPipeline

        return {
            "LivePipelineReport": LivePipelineReport,
            "LivePipelineResult": LivePipelineResult,
            "LiveTradingPipeline": LiveTradingPipeline,
        }[name]
    if name in {"LiveRuntimeOrchestrator", "RuntimeHealth"}:
        from backend.app.trading.runtime import LiveRuntimeOrchestrator, RuntimeHealth

        return {
            "LiveRuntimeOrchestrator": LiveRuntimeOrchestrator,
            "RuntimeHealth": RuntimeHealth,
        }[name]
    raise AttributeError(name)
