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
interface LayoutProps {
  children: ReactNode;
}
const Layout: React.FC<LayoutProps> = ({ children }) => {
  return (
    <div className="flex flex-col min-h-screen">
      <HeaderComponent />
      <div className="flex-1">{children}</div>
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
]);

export default router;
