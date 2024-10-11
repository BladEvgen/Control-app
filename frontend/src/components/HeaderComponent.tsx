import { apiUrl } from "../../apiConfig";
import React, {
  useState,
  useEffect,
  useRef,
  useCallback,
  useMemo,
} from "react";
import { Link, useNavigate } from "../RouterUtils";
import axiosInstance, { getCookie, setCookie, removeCookie } from "../api";
import {
  FaSignOutAlt,
  FaUpload,
  FaBars,
  FaTimes,
  FaAngleDown,
  FaUserClock,
  FaMoon,
  FaSun,
} from "react-icons/fa";
import { FaMapLocationDot } from "react-icons/fa6";
import { MdDashboard } from "react-icons/md";

type HeaderComponentProps = {
  toggleTheme: () => void;
  currentTheme: string;
};

const HeaderComponent: React.FC<HeaderComponentProps> = ({
  toggleTheme,
  currentTheme,
}) => {
  const navigate = useNavigate();
  const [username, setUsername] = useState<string>(
    () => getCookie("username") || ""
  );
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(
    () => !!getCookie("access_token")
  );
  const [isDropdownOpen, setIsDropdownOpen] = useState<boolean>(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState<boolean>(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const profileButtonRef = useRef<HTMLButtonElement>(null);

  const checkAuthentication = useCallback(async () => {
    const accessToken = getCookie("access_token");
    const refreshToken = getCookie("refresh_token");

    if (accessToken && refreshToken) {
      if (!username) {
        try {
          const userDetails = await axiosInstance.get("/user/detail/");
          const fetchedUsername = userDetails.data.user.username;

          setUsername(fetchedUsername);
          setCookie("username", fetchedUsername, { path: "/" });
          setIsAuthenticated(true);
        } catch (error) {
          console.error("Error fetching user details:", error);
          handleLogout();
        }
      } else {
        setIsAuthenticated(true);
      }
    } else {
      handleLogout();
    }
  }, [username]);

  const handleLogout = useCallback(() => {
    removeCookie("access_token");
    removeCookie("refresh_token");
    removeCookie("username");
    setIsAuthenticated(false);
    setUsername("");
    navigate("/login");
  }, [navigate]);

  useEffect(() => {
    checkAuthentication();
  }, [checkAuthentication]);

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

  const toggleDropdown = useCallback(() => {
    setIsDropdownOpen((prev) => !prev);
  }, []);

  const toggleMobileMenu = useCallback(() => {
    setIsMobileMenuOpen((prev) => !prev);
    setIsDropdownOpen(false);
  }, []);

  const DropdownMenu = useMemo(
    () => (
      <div
        ref={dropdownRef}
        className="absolute right-0 mt-2 w-48 bg-white dark:bg-gray-800 text-gray-800 dark:text-text-light rounded-md shadow-lg z-50"
        onMouseLeave={() => setIsDropdownOpen(false)}
      >
        <Link to="/dashboard">
          <button className="flex items-center px-4 py-3 hover:bg-gray-200 dark:hover:bg-gray-900 w-full text-left border-gray-300 rounded">
            <MdDashboard className="mr-2 text-blue-500" />
            Dashboard
          </button>
        </Link>
        <Link to="/map">
          <button className="flex items-center px-4 py-3 hover:bg-gray-200 dark:hover:bg-gray-900 w-full text-left border-gray-300 rounded">
            <FaMapLocationDot className="mr-2 text-yellow-500" />
            Map
          </button>
        </Link>
        <a href={`${apiUrl}/upload`}>
          <button className="flex items-center px-4 py-3 hover:bg-gray-200 dark:hover:bg-gray-900 w-full text-left border-gray-300 rounded">
            <FaUpload className="mr-2 text-green-500 hover:text-green-700" />
            Upload
          </button>
        </a>
        <button
          onClick={toggleTheme}
          className="flex items-center px-4 py-3 hover:bg-gray-200 dark:hover:bg-gray-900 w-full text-left border-t text-yellow-500"
        >
          {currentTheme === "dark" ? (
            <FaSun className="mr-2 text-yellow-500" />
          ) : (
            <FaMoon className="mr-2 text-gray-900" />
          )}
          Toggle Theme
        </button>
        <button
          onClick={handleLogout}
          className="flex items-center px-4 py-3 hover:bg-gray-200 dark:hover:bg-gray-900 w-full text-left border-t text-red-500"
        >
          <FaSignOutAlt className="mr-2" />
          Logout
        </button>
      </div>
    ),
    [currentTheme, handleLogout, toggleTheme]
  );

  const AuthenticatedMenu = useMemo(
    () => (
      <div className="relative mt-4 lg:mt-0 lg:ml-4">
        <button
          ref={profileButtonRef}
          className="flex items-center bg-primary hover:bg-primary-dark text-white font-bold py-2 px-4 rounded"
          onClick={toggleDropdown}
        >
          {username} <FaAngleDown className="ml-2" />
        </button>
        {isDropdownOpen && DropdownMenu}
      </div>
    ),
    [DropdownMenu, isDropdownOpen, toggleDropdown, username]
  );

  const UnauthenticatedMenu = useMemo(
    () => (
      <div className="flex items-center mt-4 lg:mt-0">
        <Link to="/login" className="mr-4">
          <button className="bg-primary hover:bg-primary-dark text-white font-bold py-2 px-4 rounded">
            Login
          </button>
        </Link>
        <button
          onClick={toggleTheme}
          className="bg-primary hover:bg-primary-dark text-white font-bold py-3 px-4 rounded flex items-center"
        >
          {currentTheme === "dark" ? (
            <FaSun className="text-yellow-500" />
          ) : (
            <FaMoon className="text-white" />
          )}
        </button>
      </div>
    ),
    [currentTheme, toggleTheme]
  );

  const MobileMenu = useMemo(
    () => (
      <div
        ref={dropdownRef}
        className="lg:hidden bg-primary-dark text-text-light shadow-md mt-2 p-4 rounded-md space-y-4"
      >
        <Link to="/map">
          <button className="flex items-center px-4 py-3 hover:bg-gray-200 dark:hover:bg-gray-700 w-full text-left border-gray-300 rounded">
            <FaMapLocationDot className="mr-2 text-yellow-500" />
            Map
          </button>
        </Link>
        <a
          href={`${apiUrl}/upload`}
          className="block text-lg hover:bg-primary-dark px-4 py-2 rounded-md"
        >
          <div className="flex items-center">
            <FaUpload className="mr-2 text-green-500 hover:text-green-700" />
            Upload
          </div>
        </a>
        <button
          onClick={toggleTheme}
          className=" w-full text-left text-lg hover:bg-primary-dark px-4 py-2 rounded-md flex items-center"
        >
          {currentTheme === "dark" ? (
            <FaSun className="text-yellow-500 mr-2" />
          ) : (
            <FaMoon className="text-white mr-2" />
          )}
          Toggle Theme
        </button>
        <button
          onClick={handleLogout}
          className="w-full text-left text-lg hover:bg-primary-dark px-4 py-2 rounded-md flex items-center text-red-500"
        >
          <FaSignOutAlt className="mr-2" />
          Logout
        </button>
      </div>
    ),
    [currentTheme, handleLogout, toggleTheme]
  );

  return (
    <header className="bg-primary-dark text-text-light shadow-md">
      <nav className="container mx-auto p-4 flex items-center justify-between">
        <Link
          to="/"
          className="text-2xl font-bold flex items-center text-text-light"
        >
          Staff App
          <FaUserClock className="ml-2" />
        </Link>
        <div className="flex items-center lg:hidden">
          {isAuthenticated ? (
            <button className="text-2xl mr-4" onClick={toggleMobileMenu}>
              {isMobileMenuOpen ? <FaTimes /> : <FaBars />}
            </button>
          ) : (
            UnauthenticatedMenu
          )}
        </div>
        <div className="hidden lg:flex items-center">
          {isAuthenticated ? AuthenticatedMenu : UnauthenticatedMenu}
        </div>
      </nav>
      {isMobileMenuOpen && isAuthenticated && MobileMenu}
    </header>
  );
};

export default HeaderComponent;
