import React, { useEffect, useState, ReactNode } from "react";
import { createBrowserRouter } from "react-router-dom";

const MainPage = React.lazy(() => import("./pages/MainPage.tsx"));
const HeaderComponent = React.lazy(
  () => import("./components/HeaderComponent.tsx")
);
const FooterComponent = React.lazy(
  () => import("./components/FooterComponent.tsx")
);
const LoginPage = React.lazy(() => import("./pages/LoginPage.tsx"));
const DepartmentPage = React.lazy(() => import("./pages/DepartmentPage.tsx"));
const ChildDepartmentPage = React.lazy(
  () => import("./pages/ChildDepartmentPage.tsx")
);
const StaffDetail = React.lazy(() => import("./pages/StaffDetail.tsx"));
const Dashboard = React.lazy(() => import("./pages/Dashboard.tsx"));
const MapPage = React.lazy(() => import("./pages/MapDashboard.tsx"));

import { addPrefix } from "./RouterUtils.tsx";
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
          } bg-gradient-to-b from-primary-dark via-primary-mid to-footer-light dark:via-background-darker dark:to-background-dark`}
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
        <MainPage />
      </Layout>
    ),
  },
  {
    path: addPrefix("/login"),
    element: (
      <Layout>
        <LoginPage />
      </Layout>
    ),
  },
  {
    path: addPrefix("/department/:id"),
    element: (
      <Layout>
        <DepartmentPage />{" "}
      </Layout>
    ),
  },
  {
    path: addPrefix("/childDepartment/:id"),
    element: (
      <Layout>
        <ChildDepartmentPage /> {""}
      </Layout>
    ),
  },
  {
    path: addPrefix("/staffDetail/:pin"),
    element: (
      <Layout>
        <StaffDetail /> {""}
      </Layout>
    ),
  },
  {
    path: addPrefix("/dashboard"),
    element: (
      <Layout>
        <Dashboard />
      </Layout>
    ),
  },
  {
    path: addPrefix("/map"),
    element: (
      <Layout>
        <MapPage />
      </Layout>
    ),
  },
]);

export default router;
