import React from 'react';
import { UploadInfo } from '../api';

interface HistoryListProps {
  uploads: UploadInfo[];
  onSelect: (id: number) => void;
}

const HistoryList: React.FC<HistoryListProps> = ({ uploads, onSelect }) => {
  if (!uploads || uploads.length === 0) {
    return <p className="text-sm text-muted-foreground">История загрузок пуста.</p>;
  }
  return (
    <ul className="divide-y divide-border">
      {uploads.map((item) => (
        <li
          key={item.id}
          className="py-4 flex items-center justify-between cursor-pointer hover:bg-muted/50 px-4 -mx-4 rounded-lg"
          onClick={() => onSelect(item.id)}
        >
          <div className="flex flex-col">
            <span className="font-medium">{item.filename}</span>
            <span className="text-sm text-muted-foreground">
              {new Date(item.created_at).toLocaleString('ru-RU')}
            </span>
          </div>
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="h-5 w-5 text-muted-foreground"
          >
            <path d="m9 18 6-6-6-6"></path>
          </svg>
        </li>
      ))}
    </ul>
  );
};

export default HistoryList;