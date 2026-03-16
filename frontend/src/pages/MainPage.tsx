import { memo } from "react";
import DepartmentPage from "./DepartmentPage";

const MainPage = memo(() => {
  return (
    <div>
      <DepartmentPage />
    </div>
  );
});

MainPage.displayName = "MainPage";

export default MainPage;
