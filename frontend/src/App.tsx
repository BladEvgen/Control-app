import { RouterProvider } from "react-router-dom";
import router from "./router";
import { UserProvider } from "./context/UserContext";

const App = () => {
  return (
    <UserProvider>
      <RouterProvider router={router} />
    </UserProvider>
  );
};

export default App;
