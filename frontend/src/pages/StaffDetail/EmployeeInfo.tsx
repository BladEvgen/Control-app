import React from "react";
import { motion } from "framer-motion";
import { StaffData } from "../../schemas/IData";

const bonusVariants = {
  hidden: { opacity: 0, scale: 0.9 },
  visible: { opacity: 1, scale: 1, transition: { duration: 0.5 } },
};

const CONTRACT_TYPE_CHOICES: [string, string][] = [
  ["full_time", "Полная занятость"],
  ["part_time", "Частичная занятость"],
  ["gph", "ГПХ"],
];

const getContractTypeLabel = (type: string): string => {
  const choice = CONTRACT_TYPE_CHOICES.find(([key]) => key === type);
  return choice ? choice[1] : "Не указан";
};

const shouldShowBonus = (staffData: StaffData | null): boolean => {
  if (!staffData) return false;
  if (staffData.bonus_percentage <= 0) return false;
  const excludedContractTypes = ["gph", "part_time"];
  return (
    !!staffData.contract_type &&
    !excludedContractTypes.includes(staffData.contract_type)
  );
};

interface EmployeeInfoProps {
  staffData: StaffData;
}

const EmployeeInfo: React.FC<EmployeeInfoProps> = ({ staffData }) => {
  return (
    <div className="p-8 grid grid-cols-1 md:grid-cols-2 gap-8">
      <div>
        <p className="text-xl text-gray-700 dark:text-gray-300">
          <strong>Должность:</strong> {staffData.positions.join(", ")}
        </p>
        <p className="text-xl text-gray-700 dark:text-gray-300 mt-2">
          <strong>Тип занятости:</strong>{" "}
          {getContractTypeLabel(staffData.contract_type || "")}
        </p>
        <p className="text-xl text-gray-700 dark:text-gray-300 mt-2">
          <strong>Процент за период:</strong> {staffData.percent_for_period}%
        </p>
      </div>
      {shouldShowBonus(staffData) && (
        <motion.div
          variants={bonusVariants}
          initial="hidden"
          animate="visible"
          className="flex items-center justify-center bg-green-100 dark:bg-green-900 rounded-lg p-6"
        >
          <p className="text-lg font-medium text-green-700 dark:text-green-300">
            Бонус: {staffData.bonus_percentage}%
          </p>
        </motion.div>
      )}
    </div>
  );
};

export default EmployeeInfo;
