import { ReactNode } from "react";
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
interface LayoutProps {
  children: ReactNode;
}
const Layout: React.FC<LayoutProps> = ({ children }) => {
  return (
    <div className="flex flex-col min-h-screen bg-footer-light text-dark-blue dark:text-text-light">
      <HeaderComponent />
      <div className="relative flex-1 overflow-hidden">
        <div className="absolute top-0 left-0 right-0 h-full w-full animate-drip bg-gradient-to-b from-primary-dark to-footer-light"></div>
        <div className="relative z-10 ">{children}</div>
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
    path: addPrefix("/profile"),
    element: (
      <Layout>
        <Dashboard />
      </Layout>
    ),
  },
]);

export default router;
