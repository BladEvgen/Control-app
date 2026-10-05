import {
  Suspense,
  lazy,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import { useLocation, useParams } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { FaChartBar, FaChevronDown } from "react-icons/fa";
import axiosInstance from "../api";
import { apiUrl } from "../../apiConfig";
import type { IChildDepartmentData } from "../schemas/IData";
import { formatDepartmentName } from "../utils/utils";
import { cacheManager } from "../utils/cache";
import LoaderComponent from "../components/LoaderComponent";
import ReportActions from "../components/ReportActions";
import SearchField from "../components/SearchField";
import { DetailHead, Pager, PersonRow } from "../components/Explorer";
import { useReportDates } from "../hooks/useReportDates";
import { runAttendanceExcelDownload } from "../utils/attendanceExcelDownloadHub";

const LazyDashboard = lazy(() => import("./Dashboard"));
const PAGE_SIZE = 60;

const photoUrl = (avatar: string | null): string | null =>
  avatar ? (/^https?:/.test(avatar) ? avatar : `${apiUrl}${avatar}`) : null;

export default function ChildDepartmentPage() {
  const { id } = useParams<{ id: string }>();
  const directOnly =
    new URLSearchParams(useLocation().search).get("direct") === "1";
  const [data, setData] = useState<IChildDepartmentData | null>(null);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const [showChart, setShowChart] = useState(false);
  const { startDate, endDate, setStartDate, setEndDate, today } =
    useReportDates();

  useEffect(() => {
    if (!id) return;
    const controller = new AbortController();
    const cacheKey = `child_department_${id}${directOnly ? "_direct" : ""}`;
    setQuery("");
    setPage(0);
    setError(false);
    if (attempt === 0) {
      const cached = cacheManager.get<IChildDepartmentData>(cacheKey);
      if (cached) {
        setData(cached);
        return;
      }
    } else cacheManager.invalidate(cacheKey);
    setData(null);
    axiosInstance
      .get<IChildDepartmentData>(
        `${apiUrl}/api/child_department/${id}/${directOnly ? "?direct=1" : ""}`,
        { signal: controller.signal },
      )
      .then(({ data: payload }) => {
        cacheManager.set(cacheKey, payload);
        setData(payload);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        console.error("Child department load failed:", err);
        setError(true);
      });
    return () => controller.abort();
  }, [id, directOnly, attempt]);

  const handleDownload = useCallback(() => {
    if (!id) return;
    const name = (data?.child_department.name || id).replace(/\s/g, "_");
    void runAttendanceExcelDownload({
      url: `${apiUrl}/api/download/${id}/`,
      params: { startDate, endDate },
      filename: `Посещаемость_${name}.xlsx`,
      holdKey: id,
    });
  }, [id, data, startDate, endDate]);

  const people = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase("ru");
    return Object.entries(data?.staff_data ?? {})
      .filter(([, staff]) =>
        (staff.FIO ?? "").toLocaleLowerCase("ru").includes(needle),
      )
      .sort(([, a], [, b]) =>
        (a.FIO ?? "").localeCompare(b.FIO ?? "", "ru", { numeric: true }),
      );
  }, [data, query]);
  const pageCount = Math.max(1, Math.ceil(people.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount - 1);
  const visible = people.slice(
    currentPage * PAGE_SIZE,
    (currentPage + 1) * PAGE_SIZE,
  );

  if (error)
    return (
      <div className="ws-error" role="alert">
        <span>Не удалось загрузить список людей.</span>
        <button
          type="button"
          className="ws-link-button"
          onClick={() => setAttempt((n) => n + 1)}
        >
          Повторить
        </button>
      </div>
    );
  if (!data || !id)
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
        title={formatDepartmentName(data.child_department.name)}
        meta={`${data.staff_count.toLocaleString("ru-RU")} человек`}
        actions={
          <ReportActions
            startDate={startDate}
            endDate={endDate}
            setStartDate={setStartDate}
            setEndDate={setEndDate}
            today={today}
            onDownload={handleDownload}
            holdKey={id}
          />
        }
      />

      <button
        type="button"
        className="ws-collapse-trigger"
        onClick={() => setShowChart((open) => !open)}
        aria-expanded={showChart}
        aria-controls="department-daily-chart"
      >
        <span>
          <FaChartBar aria-hidden />
          Посещаемость за день
        </span>
        <FaChevronDown className="ws-chevron" aria-hidden />
      </button>
      <AnimatePresence initial={false}>
        {showChart && (
          <motion.div
            id="department-daily-chart"
            style={{ overflow: "hidden" }}
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
          >
            <div style={{ paddingTop: 16 }}>
              <Suspense
                fallback={
                  <LoaderComponent
                    fullscreen={false}
                    showGlow={false}
                    className="py-12"
                    message=""
                  />
                }
              >
                <LazyDashboard pin={id} />
              </Suspense>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="list-head">
        <h2>
          Люди<span>{people.length}</span>
        </h2>
        <SearchField
          value={query}
          onChange={(value) => {
            setQuery(value);
            setPage(0);
          }}
          placeholder="Найти человека по ФИО"
        />
      </div>
      {visible.length ? (
        <ul className="row-list" key={currentPage}>
          {visible.map(([pin, staff], index) => (
            <PersonRow
              key={pin}
              index={index}
              to={`/staffDetail/${encodeURIComponent(pin)}`}
              name={staff.FIO || pin}
              sub={staff.positions.join(", ")}
              photo={photoUrl(staff.avatar)}
            />
          ))}
        </ul>
      ) : (
        <p className="ws-empty">
          {query ? "Никого не найдено" : "В подразделении нет людей"}
        </p>
      )}
      <Pager page={currentPage} pageCount={pageCount} onPage={setPage} />
    </>
  );
}
