import React, { useEffect, useState, ReactNode } from "react";
import { createBrowserRouter } from "react-router-dom";

import MainPage from "./pages/MainPage.tsx";
import HeaderComponent from "./components/HeaderComponent.tsx";
import FooterComponent from "./components/FooterComponent.tsx";
import LoginPage from "./pages/LoginPage.tsx";
import DepartmentPage from "./pages/DepartmentPage.tsx";
import ChildDepartmentPage from "./pages/ChildDepartmentPage.tsx";
import StaffDetail from "./pages/StaffDetail.tsx";
import { addPrefix } from "./RouterUtils.tsx";
import Dashboard from "./pages/Dashboard.tsx";
import MapPage from "./pages/MapDashboard.tsx";
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
