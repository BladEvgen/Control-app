import { Suspense } from "react";
import { createBrowserRouter, Outlet } from "react-router-dom";
import LoaderComponent from "./components/LoaderComponent";
import ErrorFallback from "./components/ErrorFallback";
import { addPrefix } from "./RouterUtils";
import Layout from "./Layout";
import RequireAuth from "./RequireAuth";
import { lazyWithRetry } from "./utils/lazyWithRetry";
import LoginPage from "./pages/LoginPage";

const PasswordResetPage = lazyWithRetry(
  () => import("./pages/PasswordResetPage"),
);

const MainPage = lazyWithRetry(() => import("./pages/MainPage"));
const DepartmentPage = lazyWithRetry(() => import("./pages/DepartmentPage"));
const ChildDepartmentPage = lazyWithRetry(
  () => import("./pages/ChildDepartmentPage"),
);
const StaffDetail = lazyWithRetry(
  () => import("./pages/StaffDetail/StaffDetail"),
);
const Dashboard = lazyWithRetry(() => import("./pages/Dashboard"));
const MapPage = lazyWithRetry(() => import("./pages/MapDashboard"));
const PhotoDashboard = lazyWithRetry(() => import("./pages/PhotoDashboard"));
const FaceLabPage = lazyWithRetry(() => import("./pages/FaceLabPage"));
const ImportPage = lazyWithRetry(() => import("./pages/ImportPage"));

const router = createBrowserRouter([
  {
    element: (
      <Layout>
        <Suspense
          fallback={
            <LoaderComponent
              fullscreen={false}
              showGlow={false}
              className="py-24"
              message=""
            />
          }
        >
          <Outlet />
        </Suspense>
      </Layout>
    ),
    errorElement: (
      <Layout>
        <ErrorFallback />
      </Layout>
    ),
    children: [
      { path: addPrefix("/login"), element: <LoginPage /> },
      { path: addPrefix("/password-reset"), element: <PasswordResetPage /> },
      {
        path: addPrefix("/password-reset/:token"),
        element: <PasswordResetPage />,
      },

      {
        element: <RequireAuth />,
        children: [
          { path: addPrefix("/"), element: <MainPage /> },
          { path: addPrefix("/department/:id"), element: <DepartmentPage /> },
          {
            path: addPrefix("/childDepartment/:id"),
            element: <ChildDepartmentPage />,
          },
          { path: addPrefix("/staffDetail/:pin"), element: <StaffDetail /> },
          { path: addPrefix("/dashboard"), element: <Dashboard /> },
          { path: addPrefix("/map"), element: <MapPage /> },
          { path: addPrefix("/photo"), element: <PhotoDashboard /> },
          { path: addPrefix("/face-lab"), element: <FaceLabPage /> },
          { path: addPrefix("/import"), element: <ImportPage /> },
        ],
      },
    ],
  },
]);

export default router;
