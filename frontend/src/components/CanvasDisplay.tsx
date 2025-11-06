import React, { useEffect, useRef } from 'react';

interface CanvasDisplayProps {
  data: Array<Record<string, any>>;
}

/**
 * Render a simple visualisation of the scene list on an HTML5 canvas.
 * Each scene is represented as a coloured bar with its number and
 * location.  This component is intentionally simple; you can extend
 * it with drag‑and‑drop, zooming or other interactive features.
 */
const CanvasDisplay: React.FC<CanvasDisplayProps> = ({ data }) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    // Adjust canvas height based on the number of scenes
    const height = Math.max(200, data.length * 60);
    canvas.height = height;
    canvas.width = 600;
    // Clear
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    data.forEach((row, idx) => {
      const y = idx * 60;
      // Alternate colours for readability
      ctx.fillStyle = idx % 2 === 0 ? '#FFAE52' : '#FF841C';
      ctx.fillRect(10, y + 10, 580, 40);
      ctx.fillStyle = '#000000';
      ctx.font = '16px sans-serif';
      ctx.fillText(`Сцена ${row['scene_number']}: ${row['location']}`, 20, y + 35);
    });
  }, [data]);

  return (
    <div className="overflow-auto border border-gray-200 dark:border-gray-700 rounded-lg">
      <canvas ref={canvasRef} className="w-full"></canvas>
    </div>
  );
};

export default CanvasDisplay;