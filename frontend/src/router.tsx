import { ReactNode } from "react";
import { createBrowserRouter } from "react-router-dom";

import MainPage from "./pages/MainPage.tsx";
import HeaderComponent from "./components/HeaderComponent.tsx";
import LoginPage from "./pages/LoginPage.tsx";
import DepartmentPage from "./pages/DepartmentPage.tsx";
import ChildDepartmentPage from "./pages/ChildDepartmentPage.tsx";
interface LayoutProps {
  children: ReactNode;
}

const Layout: React.FC<LayoutProps> = ({ children }) => {
  return (
    <div>
      <HeaderComponent />
      {children}
    </div>
  );
};

const router = createBrowserRouter([
  {
    path: "/",
    element: (
      <Layout>
        <MainPage />
      </Layout>
    ),
  },
  {
    path: "/login",
    element: (
      <Layout>
        <LoginPage />
      </Layout>
    ),
  },
  {
    path: "/department/:id",
    element: (
      <Layout>
        <DepartmentPage />{" "}
      </Layout>
    ),
  },
  {
    path: "/childDepartment/:id",
    element: (
      <Layout>
        <ChildDepartmentPage /> {""}
      </Layout>
    ),
  },
]);

export default router;
