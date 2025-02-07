import React, { useEffect, useState, ReactNode, lazy, Suspense } from "react";
import { createBrowserRouter } from "react-router-dom";

import LoaderComponent from "./components/LoaderComponent.tsx";
import HeaderComponent from "./components/HeaderComponent.tsx";
import FooterComponent from "./components/FooterComponent.tsx";
import { addPrefix } from "./RouterUtils.tsx";

const MainPage = lazy(() => import("./pages/MainPage.tsx"));
const LoginPage = lazy(() => import("./pages/LoginPage.tsx"));
const DepartmentPage = lazy(() => import("./pages/DepartmentPage.tsx"));
const ChildDepartmentPage = lazy(
  () => import("./pages/ChildDepartmentPage.tsx")
);
const StaffDetail = lazy(() => import("./pages/StaffDetail/StaffDetail.tsx"));
const Dashboard = lazy(() => import("./pages/Dashboard.tsx"));
const MapPage = lazy(() => import("./pages/MapDashboard.tsx"));
const PhotoDashboard = lazy(() => import("./pages/PhotoDashboard.tsx"));

interface LayoutProps {
  children: ReactNode;
}
const Layout: React.FC<LayoutProps> = ({ children }) => {
  const [theme, setTheme] = useState<string>(
    () => localStorage.getItem("theme") || "light"
  );

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    localStorage.setItem("theme", theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme(theme === "dark" ? "light" : "dark");
  };

  return (
    <div
      className={`flex flex-col min-h-screen bg-footer-light text-dark-blue dark:bg-background-dark dark:text-text-light`}
    >
      <HeaderComponent toggleTheme={toggleTheme} currentTheme={theme} />
      <div className="relative flex-1 overflow-hidden">
        <div
          className={`absolute top-0 left-0 right-0 h-full w-full ${
            theme === "dark" ? "animate-dripDark" : "animate-drip"
          } bg-gradient-to-b from-primary-dark via-primary-mid to-footer-light  dark:to-background-dark`}
        ></div>
        <div className="relative z-10 animate-fadeIn">{children}</div>
      </div>
      <FooterComponent />
    </div>
  );
};

const router = createBrowserRouter([
  {
    path: addPrefix("/"),
    element: (
      <Layout>
        <Suspense fallback={<LoaderComponent />}>
          <MainPage />
        </Suspense>
      </Layout>
    ),
  },
  {
    path: addPrefix("/login"),
    element: (
      <Layout>
        <Suspense fallback={<LoaderComponent />}>
          <LoginPage />
        </Suspense>
      </Layout>
    ),
  },
  {
    path: addPrefix("/department/:id"),
    element: (
      <Layout>
        <Suspense fallback={<LoaderComponent />}>
          <DepartmentPage />
        </Suspense>
      </Layout>
    ),
  },
  {
    path: addPrefix("/childDepartment/:id"),
    element: (
      <Layout>
        <Suspense fallback={<LoaderComponent />}>
          <ChildDepartmentPage />
        </Suspense>
      </Layout>
    ),
  },
  {
    path: addPrefix("/staffDetail/:pin"),
    element: (
      <Layout>
        <Suspense fallback={<LoaderComponent />}>
          <StaffDetail />
        </Suspense>
      </Layout>
    ),
  },
  {
    path: addPrefix("/dashboard"),
    element: (
      <Layout>
        <Suspense fallback={<LoaderComponent />}>
          <Dashboard />
        </Suspense>
      </Layout>
    ),
  },
  {
    path: addPrefix("/map"),
    element: (
      <Layout>
        <Suspense fallback={<LoaderComponent />}>
          <MapPage />
        </Suspense>
      </Layout>
    ),
  },
  {
    path: addPrefix("/photo"),
    element: (
      <Layout>
        <Suspense fallback={<LoaderComponent />}>
          <PhotoDashboard />
        </Suspense>
      </Layout>
    ),
  },
]);

export default router;
