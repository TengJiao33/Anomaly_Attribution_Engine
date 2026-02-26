import MapContainer from './components/MapContainer';
import DashboardOverlay from './components/DashboardOverlay';

function App() {
  return (
    <div className="relative w-screen h-screen overflow-hidden bg-slate-900">
      <MapContainer />
      <DashboardOverlay />
    </div>
  );
}

export default App;
