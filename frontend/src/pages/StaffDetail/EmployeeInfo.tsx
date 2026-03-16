import React from "react";
import { motion } from "framer-motion";
import { StaffData } from "../../schemas/IData";

const bonusVariants = {
  hidden: { opacity: 0, scale: 0.9 },
  visible: { opacity: 1, scale: 1, transition: { duration: 0.5 } },
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
  if (!shouldShowBonus(staffData)) {
    return null;
  }

  return (
    <div className="hidden sm:block px-6 lg:px-8 pb-4">
      <motion.div
        variants={bonusVariants}
        initial="hidden"
        animate="visible"
        className="inline-flex items-center gap-3 bg-gradient-to-r from-green-100 to-emerald-100 dark:from-green-900/30 dark:to-emerald-900/30 rounded-lg px-6 py-3 border-2 border-green-200 dark:border-green-800 shadow-sm"
      >
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-green-700 dark:text-green-400">
            Возможный бонус:
          </span>
          <span className="text-2xl font-bold text-green-800 dark:text-green-300">
            {staffData.bonus_percentage}%
          </span>
        </div>
      </motion.div>
    </div>
  );
};

export default EmployeeInfo;
