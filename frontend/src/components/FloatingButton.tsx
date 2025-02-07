import React, { FC } from "react";
import { createPortal } from "react-dom";
import { motion } from "framer-motion";
import { Link } from "../RouterUtils"; 


const buttonVariants = {
  hover: { scale: 1.1, transition: { duration: 0.2 } },
  tap: { scale: 0.95, transition: { duration: 0.1 } },
};

export interface FloatingButtonProps {
  /**
   * If specified, the button will be wrapped in a Link with the given address.
   */
  to?: string;
  /**
   * Click handler if the non-link button variant is used.
   */
  onClick?: () => void;
  /**
   * Button horizontal position: 'left' or 'right'. Default is 'right'.
   */
  position?: "left" | "right";
  /**
   * Classes for button background (e.g. for TailwindCSS).
   */
  bgColor?: string;
  /**
   * Classes for button hover.
   */
  hoverBgColor?: string;
  /**
   * The icon to display inside the button.
   */
  icon: React.ReactNode;
  /**
   * If true – renders the button via the portal (i.e. attaches it to document.body).
   * If false – renders the button inline.
   */
  usePortal?: boolean;
}

/**
* FloatingButton component.
* Rendered via portal by default, which avoids influence of parent elements' CSS properties (e.g. transform).
*/
export const FloatingButton: FC<FloatingButtonProps> = ({
  to,
  onClick,
  position = "right",
  bgColor = "bg-yellow-500",
  hoverBgColor = "hover:bg-yellow-600",
  icon,
  usePortal = true,
}) => {
  const buttonContent = (
    <motion.button
      variants={buttonVariants}
      whileHover="hover"
      whileTap="tap"
      onClick={onClick}
      className={`fixed bottom-4 ${
        position === "right" ? "right-4" : "left-4"
      } ${bgColor} ${hoverBgColor} text-white rounded-full p-4 shadow-lg z-50 focus:outline-none transition-transform md:hidden`}
    >
      {icon}
    </motion.button>
  );

  const element = to ? <Link to={to}>{buttonContent}</Link> : buttonContent;

  return usePortal ? createPortal(element, document.body) : element;
};

/**
* Inline version of the button (without portal). Can be useful if you need to use the button
* inside a component where fixed positioning relative to the viewport is not required.
*/
export const InlineFloatingButton: FC<FloatingButtonProps> = (props) => {
  return <FloatingButton {...props} usePortal={false} />;
};


export default FloatingButton;
