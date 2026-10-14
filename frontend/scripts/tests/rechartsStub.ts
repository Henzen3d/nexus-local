import React from 'react'

export const ResponsiveContainer = ({ children }: any) => React.createElement('div', { className: 'recharts-responsive-container' }, children)
export const PieChart = ({ children }: any) => React.createElement('svg', { className: 'recharts-pie-chart' }, children)
export const Pie = ({ children }: any) => React.createElement('g', { className: 'recharts-pie' }, children)
export const Cell = () => React.createElement('path', { className: 'recharts-cell' })
export const BarChart = ({ children }: any) => React.createElement('svg', { className: 'recharts-bar-chart' }, children)
export const Bar = () => React.createElement('path', { className: 'recharts-bar' })
export const LineChart = ({ children }: any) => React.createElement('svg', { className: 'recharts-line-chart' }, children)
export const Line = () => React.createElement('path', { className: 'recharts-line' })
export const XAxis = () => null
export const YAxis = () => null
export const Tooltip = () => null
export const Legend = () => null
export const CartesianGrid = () => null
