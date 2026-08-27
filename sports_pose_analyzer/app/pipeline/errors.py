"""管线异常类型。"""


class PipelineCancelled(RuntimeError):
    """用户取消分析。"""
