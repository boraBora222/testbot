// LogoComponent.jsx — динамическая генерация SVG из JSON
import logoData from './cryptodeal_logo.json';

const LogoCryptoDeal = ({ size = 256, animated = false }) => {
  const { metadata, design_system, elements } = logoData;
  
  return (
    <svg 
      width={size} 
      height={size} 
      viewBox={metadata.viewBox}
      xmlns={metadata.xmlns}
      className={animated ? 'logo-animated' : ''}
      style={{
        filter: 'drop-shadow(0 0 20px rgba(16, 185, 129, 0.3))',
        transition: 'transform 0.3s ease'
      }}
    >
      <defs>
        {/* Градиенты */}
        {Object.entries(design_system.gradients).map(([key, grad]) => (
          <linearGradient 
            key={grad.id}
            id={grad.id}
            x1={grad.x1} y1={grad.y1} 
            x2={grad.x2} y2={grad.y2}
          >
            {grad.stops.map((stop, idx) => (
              <stop 
                key={idx}
                offset={stop.offset} 
                stopColor={stop.color}
                stopOpacity={stop.opacity}
              />
            ))}
          </linearGradient>
        ))}
        
        {/* Фильтры */}
        <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="8" result="coloredBlur"/>
          <feMerge>
            <feMergeNode in="coloredBlur"/>
            <feMergeNode in="SourceGraphic"/>
          </feMerge>
        </filter>
      </defs>
      
      {/* Элементы логотипа */}
      {elements.map((el) => {
        if (el.type === 'circle') {
          return (
            <circle
              key={el.id}
              cx={el.cx}
              cy={el.cy}
              r={el.r}
              fill={el.fill}
              opacity={el.opacity}
              stroke={el.stroke}
              strokeWidth={el.stroke_width}
              filter={el.filter}
            />
          );
        }
        if (el.type === 'path') {
          return (
            <path
              key={el.id}
              d={el.d}
              fill={el.fill}
              stroke={el.stroke}
              strokeWidth={el.stroke_width}
              filter={el.filter}
            />
          );
        }
        if (el.type === 'line') {
          return (
            <line
              key={el.id}
              x1={el.x1} y1={el.y1}
              x2={el.x2} y2={el.y2}
              stroke={el.stroke}
              strokeWidth={el.stroke_width}
              strokeLinecap={el.stroke_linecap}
            />
          );
        }
        return null;
      })}
    </svg>
  );
};

export default LogoCryptoDeal;