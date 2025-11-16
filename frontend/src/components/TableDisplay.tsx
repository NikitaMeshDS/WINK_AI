import React, { useState, useMemo } from 'react';

interface TableDisplayProps {
  data: Record<string, Record<string, Array<Record<string, any>>>>;
}

const TableDisplay: React.FC<TableDisplayProps> = ({ data }) => {
  const showNames = Object.keys(data);
  const [selectedShow, setSelectedShow] = useState(showNames[0]);

  const seriesNames = useMemo(() => {
    return selectedShow && data[selectedShow] ? Object.keys(data[selectedShow]) : [];
  }, [data, selectedShow]);

  const [selectedSeries, setSelectedSeries] = useState(seriesNames[0]);

  // Effect to reset series selection when show changes
  React.useEffect(() => {
    if (seriesNames.length > 0) {
      setSelectedSeries(seriesNames[0]);
    } else {
      setSelectedSeries('');
    }
  }, [seriesNames]);


  if (!data || showNames.length === 0) {
    return <p className="text-sm text-muted-foreground">Нет данных для отображения.</p>;
  }

  const selectedData = (selectedShow && selectedSeries && data[selectedShow]?.[selectedSeries]) || [];
  const columns = selectedData.length > 0 ? Object.keys(selectedData[0]) : [];

  return (
    <div className="w-full space-y-4">
      {/* Show Tabs */}
      <div className="border-b border-border">
        <nav className="-mb-px flex space-x-8" aria-label="Shows">
          {showNames.map((name) => (
            <button
              key={name}
              onClick={() => setSelectedShow(name)}
              className={`
                ${name === selectedShow
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground hover:border-gray-300'
                }
                whitespace-nowrap pb-2 px-1 border-b-2 font-semibold text-md
              `}
            >
              {name}
            </button>
          ))}
        </nav>
      </div>

      {/* Series Tabs */}
      <div className="border-b border-border">
        <nav className="-mb-px flex space-x-8" aria-label="Tabs">
          {seriesNames.map((name) => (
            <button
              key={name}
              onClick={() => setSelectedSeries(name)}
              className={`
                ${name === selectedSeries
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground hover:border-gray-300'
                }
                whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm
              `}
            >
              {name}
            </button>
          ))}
        </nav>
      </div>
      
      <div className="border rounded-lg overflow-hidden overflow-x-auto">
        <table className="min-w-full divide-y divide-border">
          <thead className="bg-muted/50">
            <tr>
              {columns.map((col) => (
                <th
                  key={col}
                  className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider"
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border bg-background">
            {selectedData.map((row, idx) => (
              <tr key={idx} className="hover:bg-muted/50">
                {columns.map((col) => (
                  <td key={col} className="px-4 py-3 whitespace-pre-wrap text-sm">
                    {String(row[col] ?? '')}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default TableDisplay;