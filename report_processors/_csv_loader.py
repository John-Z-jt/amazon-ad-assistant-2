import os
from typing import BinaryIO, Union

import pandas as pd

ReportSource = Union[str, os.PathLike, BinaryIO]

_DEFAULT_ENCODINGS = ["gbk", "utf-8", "gb2312", "gb18030"]


def _source_filename(source: ReportSource, filename: str | None = None) -> str:
    if filename:
        return filename
    if isinstance(source, (str, os.PathLike)):
        return os.fspath(source)
    return str(getattr(source, "name", "") or "")


def _is_xlsx_source(source: ReportSource, filename: str | None = None) -> bool:
    return _source_filename(source, filename).lower().endswith(".xlsx")


def _read_csv_from_path(file_path: str, report_name: str) -> pd.DataFrame:
    last_error = None
    for enc in _DEFAULT_ENCODINGS:
        try:
            return pd.read_csv(file_path, encoding=enc)
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
    raise ValueError(
        f"无法解码{report_name}，请确认文件编码为 GBK 或 UTF-8: {file_path}"
    ) from last_error


def _read_csv_from_fileobj(source: ReportSource, report_name: str) -> pd.DataFrame:
    last_error = None
    for enc in _DEFAULT_ENCODINGS:
        try:
            if hasattr(source, "seek"):
                source.seek(0)
            return pd.read_csv(source, encoding=enc)
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
        except Exception as exc:
            last_error = exc
            continue
    raise ValueError(
        f"无法解码{report_name}，请确认文件编码为 GBK 或 UTF-8。"
    ) from last_error


def _read_xlsx(source: ReportSource, report_name: str) -> pd.DataFrame:
    try:
        if isinstance(source, (str, os.PathLike)):
            return pd.read_excel(os.fspath(source), engine="openpyxl")
        if hasattr(source, "seek"):
            source.seek(0)
        return pd.read_excel(source, engine="openpyxl")
    except Exception as exc:
        raise ValueError(f"无法读取{report_name} Excel 文件，请确认格式为 .xlsx。") from exc


def read_report_file(
    source: ReportSource,
    report_name: str,
    *,
    filename: str | None = None,
) -> pd.DataFrame:
    """读取 CSV（多编码）或 xlsx 报表。"""
    if isinstance(source, (str, os.PathLike)):
        file_path = os.fspath(source)
        if not os.path.exists(file_path):
            raise ValueError(f"{report_name}文件不存在: {file_path}")
        if _is_xlsx_source(source, filename):
            return _read_xlsx(source, report_name)
        return _read_csv_from_path(file_path, report_name)

    if hasattr(source, "read"):
        if _is_xlsx_source(source, filename):
            return _read_xlsx(source, report_name)
        return _read_csv_from_fileobj(source, report_name)

    raise TypeError("source 必须是文件路径或可读的文件对象。")


def read_report_csv(source: ReportSource, report_name: str) -> pd.DataFrame:
    """按常见编码读取 CSV 报表（兼容旧调用；上传文件请用 read_report_file）。"""
    return read_report_file(source, report_name)
