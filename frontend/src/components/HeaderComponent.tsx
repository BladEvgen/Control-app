import { useState, useEffect, useRef, useCallback } from "react";
import { useLocation } from "react-router-dom";
import { Link, useNavigate } from "../RouterUtils";
import Cookies from "js-cookie";
import axiosInstance from "../api";
import { apiUrl } from "../../apiConfig";
import {
  FaUser,
  FaSignOutAlt,
  FaUpload,
  FaBars,
  FaTimes,
  FaAngleDown,
  FaUserClock,
} from "react-icons/fa";

const HeaderComponent = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState<string>("");
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [isDropdownOpen, setIsDropdownOpen] = useState<boolean>(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState<boolean>(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const profileButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    checkAuthentication();
  }, []);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node) &&
        !profileButtonRef.current?.contains(event.target as Node)
      ) {
        setIsDropdownOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  const checkAuthentication = useCallback(async () => {
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
  }, [navigate, location.pathname]);

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

  const toggleMobileMenu = () => {
    setIsMobileMenuOpen(!isMobileMenuOpen);
  };

  const handleMouseLeave = () => {
    setIsDropdownOpen(false);
  };

  return (
    <header className="bg-blue-900 text-white shadow-md">
      <nav className="container mx-auto p-4 flex items-center justify-between">
        <Link to="/" className="text-2xl font-bold flex items-center">
          <span>Staff App</span>
          <FaUserClock className="m-2" />
        </Link>
        <div className="lg:hidden">
          <button className="text-2xl" onClick={toggleMobileMenu}>
            {isMobileMenuOpen ? <FaTimes /> : <FaBars />}
          </button>
        </div>
        <div
          className={`lg:flex items-center ${
            isMobileMenuOpen ? "block" : "hidden"
          } lg:block`}
        >
          {isAuthenticated ? (
            <div className="relative mt-4 lg:mt-0 lg:ml-4">
              <button
                ref={profileButtonRef}
                className="flex items-center bg-gray-800 hover:bg-gray-900 text-white font-bold py-2 px-4 rounded relative"
                onClick={toggleDropdown}
              >
                {username} <FaAngleDown className="ml-2" />
              </button>
              {isDropdownOpen && (
                <div
                  ref={dropdownRef}
                  className="absolute right-0 mt-2 w-48 bg-white text-gray-800 rounded-md shadow-lg z-50"
                  onMouseLeave={handleMouseLeave}
                >
                  <Link to="/profile">
                    <button className="flex items-center px-4 py-3 hover:bg-gray-200 w-full text-left border-gray-300 rounded">
                      <FaUser className="mr-2 text-blue-500" />
                      Profile
                    </button>
                  </Link>
                  <a href={`${apiUrl}/upload`}>
                    <button className="flex items-center px-4 py-3  hover:bg-gray-200  w-full text-left border-gray-300">
                      <FaUpload className="mr-2 text-green-500 hover:text-green-700" />
                      Upload
                    </button>
                  </a>
                  <button
                    onClick={handleLogout}
                    className="flex items-center px-4 py-3 hover:bg-gray-200 w-full text-left border-t text-red-500"
                  >
                    <FaSignOutAlt className="mr-2" />
                    Logout
                  </button>
                </div>
              )}
            </div>
          ) : (
            location.pathname !== "/login" && (
              <Link to="/login" className="mt-4 lg:mt-0 lg:ml-4">
                <button className="bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded">
                  Login
                </button>
              </Link>
            )
          )}
        </div>
      </nav>
    </header>
  );
};

export default HeaderComponent;
