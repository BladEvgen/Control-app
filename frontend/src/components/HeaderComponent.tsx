import { useState, useEffect } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import Cookies from "js-cookie";
import { apiUrl } from "../../apiConfig";
import axiosInstance from "../api";

const HeaderComponent = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);

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

    window.location.reload();
  };

  const toggleDropdown = () => {
    setIsDropdownOpen(!isDropdownOpen);
  };

  return (
    <header className="bg-[#123075]">
      <nav className="flex items-center justify-between flex-wrap p-6">
        <div className="flex items-center flex-shrink-0 text-white mr-6">
          <Link to="/">
            <span className="font-semibold text-xl tracking-tight">
              Control Staff App
            </span>
          </Link>
        </div>
        <div className="w-full block lg:flex lg:items-center lg:w-auto">
          {isAuthenticated ? (
            <div className="text-sm lg:flex-grow">
              <div className="relative">
                <button
                  className="bg-gray-800 text-white font-bold py-2 px-4 rounded lg:inline-flex lg:w-auto"
                  onClick={toggleDropdown}>
                  {username}
                  <svg
                    className="h-5 w-5 inline-block ml-2 lg:hidden"
                    xmlns="http://www.w3.org/2000/svg"
                    viewBox="0 0 20 20"
                    fill="currentColor">
                    <path
                      fillRule="evenodd"
                      d="M9.293 13.707a1 1 0 01-1.414 0l-3-3a1 1 0 111.414-1.414L8 11.586V3a1 1 0 112 0v8.586l2.293-2.293a1 1 0 111.414 1.414l-3 3z"
                      clipRule="evenodd"
                    />
                  </svg>
                </button>
                {isDropdownOpen && (
                  <div className="absolute mt-2 w-48 bg-white rounded-md shadow-lg lg:absolute lg:right-0">
                    <button
                      onClick={handleLogout}
                      className="block px-4 py-2 text-gray-800 hover:bg-gray-200 w-full text-left">
                      Logout
                    </button>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div>
              {location.pathname !== "/login" && (
                <Link to="/login">
                  <button className="bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded">
                    Login
                  </button>
                </Link>
              )}
            </div>
          )}
          {isAuthenticated && (
            <div className="flex mt-4 lg:mt-0 lg:ml-4">
              <a
                href={`${apiUrl}/upload`}
                className="bg-green-500 hover:bg-green-700 text-white font-bold py-2 px-4 rounded lg:inline-flex lg:w-auto">
                Upload Data
              </a>
            </div>
          )}
        </div>
      </nav>
    </header>
  );
};

export default HeaderComponent;
