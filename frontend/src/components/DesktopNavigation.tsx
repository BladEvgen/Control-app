import React from "react";
import { FaHome, FaArrowLeft } from "react-icons/fa";
import ModernButton from "./ModernButton";
import { Link } from "../RouterUtils";

interface BaseProps {
  onHomeClick: () => void;
}

interface AllButtonsProps extends BaseProps {
  onBackClick: () => void;
  visibleButtons?: never;
}

interface PartialButtonsProps extends BaseProps {
  visibleButtons: Array<"home" | "back">;
  onBackClick?: () => void;
}

type DesktopNavigationProps = AllButtonsProps | PartialButtonsProps;

interface ButtonConfig {
  key: "home" | "back";
  variant: "home" | "back";
  icon: JSX.Element;
  text: string;
  onClick?: () => void;
  to?: string;
}

const DesktopNavigation: React.FC<DesktopNavigationProps> = (props) => {
  const { onHomeClick } = props;
  const visibleButtons =
    "visibleButtons" in props ? props.visibleButtons : undefined;
  const onBackClick =
    "visibleButtons" in props ? props.onBackClick : props.onBackClick;

  const buttons: ButtonConfig[] = [
    {
      key: "home",
      variant: "home",
      icon: <FaHome />,
      text: "На главную",
      to: "/",
      onClick: onHomeClick,
    },
    {
      key: "back",
      variant: "back",
      icon: <FaArrowLeft />,
      text: "Вернуться назад",
      onClick: onBackClick,
    },
  ];

  const buttonsToRender = visibleButtons
    ? buttons.filter((btn) => visibleButtons.includes(btn.key))
    : buttons;

  return (
    <div className="hidden md:flex items-end justify-between mb-6">
      <div className="flex space-x-4">
        {buttonsToRender.map((btn) => {
          if (btn.key === "home" && btn.to) {
            return (
              <Link to={btn.to} key={btn.key}>
                <ModernButton variant={btn.variant} icon={btn.icon}>
                  {btn.text}
                </ModernButton>
              </Link>
            );
          }
          if (!btn.onClick) return null;
          return (
            <ModernButton
              key={btn.key}
              variant={btn.variant}
              icon={btn.icon}
              onClick={btn.onClick}
            >
              {btn.text}
            </ModernButton>
          );
        })}
      </div>
    </div>
  );
};

export default DesktopNavigation;
