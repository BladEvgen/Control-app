import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import axiosInstance from "../api";
import { apiUrl } from "../../apiConfig";
import type { IChildDepartment, IData } from "../schemas/IData";
import { formatDepartmentName } from "../utils/utils";
import LoaderComponent from "../components/LoaderComponent";
import ReportActions from "../components/ReportActions";
import SearchField from "../components/SearchField";
import { DetailHead, UnitRow } from "../components/Explorer";
import { useReportDates } from "../hooks/useReportDates";
import { useNavigationNodes } from "../hooks/useNavigationNodes";
import { runAttendanceExcelDownload } from "../utils/attendanceExcelDownloadHub";
import { cacheManager } from "../utils/cache";
import { matchesDepartmentSearch } from "../utils/departmentNavigation";

type OwnStaff = { direct_staff_count?: number };

type RootDepartmentResponse = {
  departments: IChildDepartment[];
  display_root: {
    child_id: string;
    name: string;
    direct_staff_count: number;
  } | null;
  total_staff_count: number;
};

const ownStaffEntry = (
  id: string,
  name: string,
  count: number,
): IChildDepartment => ({
  child_id: id,
  name: `${name} — без подотдела`,
  date_of_creation: "",
  parent: id,
  has_child_departments: false,
  direct_staff_count: count,
  own_staff_only: true,
});

function departmentPath(department: IChildDepartment): string {
  const id = encodeURIComponent(department.child_id);
  if (department.own_staff_only) return `/childDepartment/${id}?direct=1`;
  return `/${department.has_child_departments ? "department" : "childDepartment"}/${id}`;
}

async function loadDepartment(departmentId: string | null): Promise<IData> {
  if (departmentId) {
    const res = await axiosInstance.get<IData & OwnStaff>(
      `${apiUrl}/api/department/${departmentId}/`,
      { timeout: 30000 },
    );
    const own = res.data.direct_staff_count ?? 0;
    const children = res.data.child_departments ?? [];
    return own > 0 && children.length
      ? {
          ...res.data,
          child_departments: [
            ...children,
            ownStaffEntry(departmentId, res.data.name, own),
          ],
        }
      : res.data;
  }
  const res = await axiosInstance.get<RootDepartmentResponse>(
    `${apiUrl}/api/departments/root/`,
  );
  const root = res.data.display_root;
  const children: IChildDepartment[] = (res.data.departments ?? []).map(
    (d) => ({
      child_id: d.child_id,
      name: d.name ?? String(d.child_id),
      date_of_creation: d.date_of_creation ?? "",
      parent: "",
      has_child_departments: d.has_child_departments ?? false,
      direct_staff_count: d.direct_staff_count ?? 0,
    }),
  );
  if (root && root.direct_staff_count > 0)
    children.push(
      ownStaffEntry(root.child_id, root.name, root.direct_staff_count),
    );
  return {
    name: root?.name ?? "Структура университета",
    date_of_creation: "",
    child_departments: children,
    total_staff_count: res.data.total_staff_count || 0,
  };
}

export default function DepartmentPage() {
  const { id } = useParams<{ id: string }>();
  const departmentId = id ?? null;
  const [data, setData] = useState<IData | null>(null);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [query, setQuery] = useState("");
  const requestSequence = useRef(0);
  const { nodes } = useNavigationNodes();
  const { startDate, endDate, setStartDate, setEndDate, today } =
    useReportDates();

  useEffect(() => {
    const request = ++requestSequence.current;
    const cacheKey = departmentId
      ? `department_${departmentId}`
      : "root_departments";
    setQuery("");
    setError(false);
    if (attempt === 0) {
      const cached = cacheManager.get<IData>(cacheKey);
      if (cached) {
        setData(cached);
        return;
      }
    } else cacheManager.invalidate(cacheKey);
    setData(null);
    loadDepartment(departmentId)
      .then((payload) => {
        cacheManager.set(cacheKey, payload);
        if (request === requestSequence.current) setData(payload);
      })
      .catch((err: unknown) => {
        if (request !== requestSequence.current) return;
        console.error("Department load failed:", err);
        setError(true);
      });
  }, [departmentId, attempt]);

  const totals = useMemo(
    () => new Map(nodes.map((node) => [node.id, node.total_staff_count])),
    [nodes],
  );
  const units = useMemo(
    () =>
      (data?.child_departments ?? [])
        .filter((unit) => matchesDepartmentSearch(unit.name, query))
        .sort(
          (a, b) =>
            Number(a.own_staff_only ?? 0) - Number(b.own_staff_only ?? 0) ||
            a.name.localeCompare(b.name, "ru", { numeric: true }),
        ),
    [data, query],
  );
  const unitCount = data?.child_departments.length ?? 0;

  const handleDownload = useCallback(() => {
    if (!departmentId) return;
    const name = (data?.name || departmentId).replace(/\s/g, "_");
    void runAttendanceExcelDownload({
      url: `${apiUrl}/api/download/${departmentId}/`,
      params: { startDate, endDate },
      filename: `Посещаемость_${name}.xlsx`,
      holdKey: departmentId,
    });
  }, [departmentId, data?.name, startDate, endDate]);

  if (error)
    return (
      <div className="ws-error" role="alert">
        <span>Не удалось загрузить подразделение.</span>
        <button
          type="button"
          className="ws-link-button"
          onClick={() => setAttempt((n) => n + 1)}
        >
          Повторить
        </button>
      </div>
    );
  if (!data)
    return (
      <LoaderComponent
        fullscreen={false}
        showGlow={false}
        className="py-24"
        message=""
      />
    );

  return (
    <>
      <DetailHead
        path={data.breadcrumb_path}
        title={formatDepartmentName(data.name)}
        meta={`${data.total_staff_count.toLocaleString("ru-RU")} человек`}
        actions={
          departmentId ? (
            <ReportActions
              startDate={startDate}
              endDate={endDate}
              setStartDate={setStartDate}
              setEndDate={setEndDate}
              today={today}
              onDownload={handleDownload}
              holdKey={departmentId}
            />
          ) : undefined
        }
      />
      <div className="list-head">
        <h2>
          Подразделения<span>{unitCount}</span>
        </h2>
        {unitCount > 1 && (
          <SearchField
            value={query}
            onChange={setQuery}
            placeholder="Найти подразделение в этом списке"
          />
        )}
      </div>
      {units.length ? (
        <ul className="row-list">
          {units.map((unit, index) => (
            <UnitRow
              key={`${unit.child_id}-${unit.own_staff_only ? "own" : ""}`}
              index={index}
              to={departmentPath(unit)}
              name={formatDepartmentName(unit.name)}
              folder={unit.has_child_departments}
              count={
                unit.own_staff_only
                  ? unit.direct_staff_count
                  : totals.get(String(unit.child_id))
              }
            />
          ))}
        </ul>
      ) : (
        <p className="ws-empty">
          {query ? "Ничего не найдено" : "Подразделений нет"}
        </p>
      )}
    </>
  );
}
