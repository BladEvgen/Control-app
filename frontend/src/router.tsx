import { lazy, Suspense } from "react";
import { createBrowserRouter, Outlet } from "react-router-dom";
import LoaderComponent from "./components/LoaderComponent";
import { addPrefix } from "./RouterUtils";
import Layout from "./Layout";

const MainPage = lazy(() => import("./pages/MainPage"));
const LoginPage = lazy(() => import("./pages/LoginPage"));
const DepartmentPage = lazy(() => import("./pages/DepartmentPage"));
const ChildDepartmentPage = lazy(() => import("./pages/ChildDepartmentPage"));
const StaffDetail = lazy(() => import("./pages/StaffDetail/StaffDetail"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const MapPage = lazy(() => import("./pages/MapDashboard"));
const PhotoDashboard = lazy(() => import("./pages/PhotoDashboard"));

const router = createBrowserRouter([
  {
    element: (
      <Layout>
        <Suspense fallback={<LoaderComponent />}>
          <Outlet />
        </Suspense>
      </Layout>
    ),
    children: [
      { path: addPrefix("/"), element: <MainPage /> },
      { path: addPrefix("/login"), element: <LoginPage /> },
      { path: addPrefix("/department/:id"), element: <DepartmentPage /> },
      {
        path: addPrefix("/childDepartment/:id"),
        element: <ChildDepartmentPage />,
      },
      { path: addPrefix("/staffDetail/:pin"), element: <StaffDetail /> },
      { path: addPrefix("/dashboard"), element: <Dashboard /> },
      { path: addPrefix("/map"), element: <MapPage /> },
      { path: addPrefix("/photo"), element: <PhotoDashboard /> },
    ],
  },
]);

export default router;
