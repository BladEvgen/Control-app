import { Suspense } from "react";
import { createBrowserRouter, Outlet } from "react-router-dom";
import LoaderComponent from "./components/LoaderComponent";
import ErrorFallback from "./components/ErrorFallback";
import { addPrefix } from "./RouterUtils";
import Layout from "./Layout";
import RequireAuth from "./RequireAuth";
import { lazyWithRetry } from "./utils/lazyWithRetry";
import LoginPage from "./pages/LoginPage";

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

const router = createBrowserRouter([
  {
    element: (
      <Layout>
        <Suspense fallback={<LoaderComponent />}>
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
        ],
      },
    ],
  },
]);

export default router;
