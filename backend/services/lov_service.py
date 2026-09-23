import csv
import io
import re
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from core.storage_layout import get_lov_upload_dir
from core.config import LOV_FILE_EXTENSION


_UPLOAD_PREFIX = re.compile(r"^[0-9a-f]{32}_")


def strip_upload_prefix(filename: str) -> str:
    return _UPLOAD_PREFIX.sub("", filename)


class LovService:
    @staticmethod
    def _extract_sheet_lovs(
        profile_map: Path,
        sheet: str,
    ) -> set[str]:
        workbook = load_workbook(profile_map, read_only=True, data_only=True)

        try:
            worksheet = workbook[sheet]
            rows = worksheet.iter_rows(values_only=True)
            headers = [str(column or "").strip() for column in next(rows, ())]

            rules_column_single = "Applicable Rule\n(Single ID)"
            rules_column_legacy = "Applicable Rules\n(comma-sep IDs)"
            parameters_column = "Rule Parameters\n(see Instructions)"

            rules_column = rules_column_single if rules_column_single in headers else rules_column_legacy

            if rules_column not in headers:
                return set()

            lovs: set[str] = set()
            for row in rows:
                record = dict(zip(headers, row))

                rules = str(record.get(rules_column) or "").strip().upper()
                rule_list = [r.strip() for r in rules.replace(",", "|").replace(";", "|").split("|") if r.strip()]

                if "DQ8" not in rule_list:
                    continue

                parameters = str(record.get(parameters_column) or "").strip()
                parts = [
                    part.strip()
                    for part in parameters.split("|")
                    if part.strip()
                ]
                if parts:
                    lovs.add(parts[0])

            return lovs
        finally:
            workbook.close()

    def extract_required_lovs(
        self,
        profile_map_path: str | Path | None,
    ) -> set[str]:
        required: set[str] = set()

        if not profile_map_path:
            return required

        profile_map = Path(profile_map_path)

        if not profile_map.exists():
            return required

        try:
            excel_file = load_workbook(
                profile_map,
                read_only=True,
                data_only=True,
            )

            try:
                for sheet in excel_file.sheetnames:
                    if sheet.lower() == "instructions":
                        continue

                    required.update(
                        self._extract_sheet_lovs(profile_map, sheet)
                    )
            finally:
                excel_file.close()

        except Exception as exc:
            print(
                "[WARN] Could not extract DQ8 LOVs "
                f"from profile map: {exc}"
            )

        return required

    @staticmethod
    def summarize_csv(text: str) -> list[dict[str, Any]]:
        reader = csv.reader(io.StringIO(text))

        header = next(reader, None)
        if not header:
            return []

        names = [str(cell or "").strip() for cell in header]
        counts = [0] * len(names)

        for row in reader:
            for index in range(min(len(row), len(names))):
                if str(row[index] or "").strip():
                    counts[index] += 1

        return [
            {"name": name, "values_count": counts[index]}
            for index, name in enumerate(names)
            if name
        ]

    @staticmethod
    def _read_text(path: Path) -> str:
        return path.read_text(encoding="utf-8-sig")

    def list_lov_files(self) -> list[dict[str, Any]]:
        return self._list_lov_files_local()

    def _list_lov_files_local(self) -> list[dict[str, Any]]:
        directory = get_lov_upload_dir()

        if not directory.is_dir():
            return []

        files: list[dict[str, Any]] = []

        for path in sorted(directory.iterdir()):
            if not path.is_file() or path.suffix.lower() != LOV_FILE_EXTENSION:
                continue

            try:
                lovs = self.summarize_csv(self._read_text(path))
            except Exception as exc:
                print(f"[WARN] Could not read LOV file {path.name}: {exc}")
                lovs = []

            files.append(self._build_entry(path.name, lovs))

        return files

    @staticmethod
    def _build_entry(filename: str, lovs: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "file": filename,
            "display_name": strip_upload_prefix(filename),
            "lovs": lovs,
        }

    def get_lov_file(self, filename: str) -> dict[str, Any] | None:
        if not filename or "/" in filename or "\\" in filename or ".." in filename:
            return None

        if not filename.lower().endswith(LOV_FILE_EXTENSION):
            return None

        directory = get_lov_upload_dir()
        target = directory / filename

        if not target.is_file():
            return None

        try:
            lovs = self.summarize_csv(self._read_text(target))
        except Exception as exc:
            print(f"[WARN] Could not read LOV file {filename}: {exc}")
            lovs = []

        return self._build_entry(filename, lovs)

    def delete_lov_file(self, filename: str) -> bool:
        directory = get_lov_upload_dir()
        target = directory / filename

        if target.resolve().parent != directory.resolve():
            raise ValueError("Invalid filename")

        if not target.is_file():
            return False

        target.unlink()
        return True

    def discover_lov_files(
        self,
        lov_dir: str | Path | None = None,
        lov_file: str | None = None,
    ) -> dict[str, str]:
        discovered: dict[str, str] = {}

        directory = (
            Path(lov_dir)
            if lov_dir
            else get_lov_upload_dir()
        )

        if not directory.is_dir():
            return discovered

        try:
            for path in sorted(directory.iterdir()):
                if not path.is_file():
                    continue

                if path.suffix.lower() != LOV_FILE_EXTENSION:
                    continue

                if lov_file and path.name != lov_file:
                    continue

                try:
                    columns = self.summarize_csv(self._read_text(path))
                except Exception as exc:
                    print(
                        "[WARN] Could not read header from "
                        f"{path.name}, using filename: {exc}"
                    )
                    discovered.setdefault(
                        strip_upload_prefix(path.stem),
                        str(path),
                    )
                    continue

                for column in columns:
                    name = column["name"]

                    if name in discovered and discovered[name] != str(path):
                        print(
                            f"[WARN] LOV '{name}' is defined in more than one "
                            f"file; keeping '{Path(discovered[name]).name}'"
                        )
                        continue

                    discovered[name] = str(path)

        except Exception as exc:
            print(
                f"[WARN] LOV discovery failed: {exc}"
            )

        return discovered

    def build_lov_configuration(
        self,
        profile_map_path: str | Path | None,
        lov_dir: str | Path | None = None,
        lov_file: str | None = None,
    ) -> dict[str, str]:
        required_lovs = self.extract_required_lovs(
            profile_map_path
        )

        available_lovs = self.discover_lov_files(
            lov_dir,
            lov_file=lov_file,
        )

        lov_configuration: dict[str, str] = {}

        for lov_name in required_lovs:
            if lov_name in available_lovs:
                lov_configuration[lov_name] = (
                    available_lovs[lov_name]
                )
                print(
                    f"[INFO] Added required LOV: {lov_name}"
                )
            else:
                print(
                    "[WARN] Required LOV "
                    f"'{lov_name}' not found in uploads/lov/"
                )

        if not required_lovs:
            print(
                "[INFO] No DQ8 rules found, "
                "skipping LOV tables"
            )

        return lov_configuration


lov_service = LovService()
