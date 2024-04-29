import AppBar from "@mui/material/AppBar";
import Box from "@mui/material/Box";
import Toolbar from "@mui/material/Toolbar";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import { Link, useLocation, useNavigate } from "react-router-dom";
import Cookies from "js-cookie";
import { useState, useEffect } from "react";
import axiosInstance from "../api";

const HeaderComponent = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  useEffect(() => {
    checkAuthentication();
  }, []);

  const checkAuthentication = async () => {
    const accessToken = Cookies.get("access_token");
    const refreshToken = Cookies.get("refresh_token");

    if (accessToken && refreshToken) {
      try {
        const userDetails = await axiosInstance.get("/user/detail/");
        setUsername(userDetails.data.user.username);
        setIsAuthenticated(true);
      } catch (error) {
        console.error("Error fetching user details:", error);
        setIsAuthenticated(false);
      }
    } else {
      setIsAuthenticated(false);
      if (location.pathname !== "/login") {
        navigate("/login");
      }
    }
  };

  const handleLogout = () => {
    Cookies.remove("access_token");
    Cookies.remove("refresh_token");
    Cookies.remove("sessionid");
    setIsAuthenticated(false);
    navigate("/");
  };

  return (
    <Box sx={{ flexGrow: 1 }}>
      <AppBar position="static">
        <Toolbar>
          <Typography variant="h6" component={Link} to="/" sx={{ flexGrow: 1 }}>
            {" "}
            Contracts manager
          </Typography>
          {!isAuthenticated && (
            <>
              <Button
                variant="contained"
                color="primary"
                onClick={() => navigate("/login")}>
                Login
              </Button>
            </>
          )}
          {isAuthenticated && (
            <>
              <Box
                sx={{
                  fontSize: "16px",
                  fontWeight: "bold",
                  padding: "10px",
                  marginRight: "10px",
                  color: "orange",
                }}>
                {username.toUpperCase()}
              </Box>
              <Button
                variant="contained"
                color="error"
                sx={{ marginLeft: "10px" }}
                onClick={handleLogout}>
                Logout
              </Button>
            </>
          )}
        </Toolbar>
      </AppBar>
    </Box>
  );
};

export default HeaderComponent;
