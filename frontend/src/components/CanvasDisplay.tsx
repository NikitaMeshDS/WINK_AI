import React, { useEffect, useRef, useState, useMemo } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader';
import { DRACOLoader } from 'three/examples/jsm/loaders/DRACOLoader';
import { TransformControls } from 'three/examples/jsm/controls/TransformControls';

interface CanvasDisplayProps {
  data: Record<string, Record<string, Array<Record<string, any>>>>;
}

const CanvasDisplay: React.FC<CanvasDisplayProps> = ({ data }) => {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const showNames = Object.keys(data);
  const [selectedShow, setSelectedShow] = useState(showNames[0]);
  
  const seriesNames = useMemo(() => {
    return selectedShow && data[selectedShow] ? Object.keys(data[selectedShow]) : [];
  }, [data, selectedShow]);

  const [selectedSeries, setSelectedSeries] = useState(seriesNames[0]);
  const [mode, setMode] = useState<'translate' | 'rotate' | 'scale'>('translate');

  // Effect to reset series selection when show changes
  React.useEffect(() => {
    if (seriesNames.length > 0) {
      setSelectedSeries(seriesNames[0]);
    } else {
      setSelectedSeries('');
    }
  }, [seriesNames]);

  useEffect(() => {
    if (!mountRef.current) return;

    const currentMount = mountRef.current;
    let scene: THREE.Scene, camera: THREE.PerspectiveCamera, renderer: THREE.WebGLRenderer;
    let orbitControls: OrbitControls, transformControls: TransformControls;
    const mixers: THREE.AnimationMixer[] = [];
    const clock = new THREE.Clock();
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();

    // Scene setup
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x222222);
    scene.fog = new THREE.Fog(0x222222, 20, 100);

    // Camera setup
    camera = new THREE.PerspectiveCamera(75, currentMount.clientWidth / currentMount.clientHeight, 0.1, 1000);
    camera.position.set(2, 8, 15);

    // Renderer setup
    renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(currentMount.clientWidth, currentMount.clientHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.shadowMap.enabled = true;
    currentMount.appendChild(renderer.domElement);

    // Controls
    orbitControls = new OrbitControls(camera, renderer.domElement);
    orbitControls.enableDamping = true;
    orbitControls.dampingFactor = 0.1;
    orbitControls.screenSpacePanning = false;
    orbitControls.maxPolarAngle = Math.PI / 2.1;

    // Lighting
    const hemiLight = new THREE.HemisphereLight(0xffffff, 0x444444);
    hemiLight.position.set(0, 20, 0);
    scene.add(hemiLight);

    const dirLight = new THREE.DirectionalLight(0xffffff);
    dirLight.position.set(3, 10, 10);
    dirLight.castShadow = true;
    dirLight.shadow.camera.top = 10;
    dirLight.shadow.camera.bottom = -10;
    dirLight.shadow.camera.left = -10;
    dirLight.shadow.camera.right = 10;
    dirLight.shadow.camera.near = 0.1;
    dirLight.shadow.camera.far = 40;
    scene.add(dirLight);

    // Floor
    const floor = new THREE.Mesh(
      new THREE.PlaneGeometry(100, 100),
      new THREE.MeshPhongMaterial({ color: 0x555555, depthWrite: false })
    );
    floor.rotation.x = -Math.PI / 2;
    floor.receiveShadow = true;
    scene.add(floor);

    // Transform Controls
    transformControls = new TransformControls(camera, renderer.domElement);
    transformControls.addEventListener('dragging-changed', (event) => {
      orbitControls.enabled = !event.value;
    });
    
    // Workaround for potential module resolution issues
    try {
      scene.add(transformControls);
    } catch (e) {
      console.error("Failed to add TransformControls to scene directly, attempting workaround.", e);
      scene.add(transformControls.gizmo);
      scene.add(transformControls.plane);
    }

    const objects: THREE.Object3D[] = [];

    const addActor = () => {
      const loader = new GLTFLoader();
      const dracoLoader = new DRACOLoader();
      dracoLoader.setDecoderPath('/draco/');
      loader.setDRACOLoader(dracoLoader);

      loader.load('https://threejs.org/examples/models/gltf/Soldier.glb', (gltf) => {
        const model = gltf.scene;
        model.traverse(function (object: any) {
          if (object.isMesh) object.castShadow = true;
        });
        const animations = gltf.animations;
        const mixer = new THREE.AnimationMixer(model);
        mixers.push(mixer);
        const walkAction = mixer.clipAction(animations.find(anim => anim.name === 'Walk')!);
        walkAction.play();
        
        const newPositionX = (objects.length - 2) * 2;
        model.position.set(newPositionX, 0, 0);
        scene.add(model);
        objects.push(model);
      }, undefined, (error) => {
        console.error('An error happened while loading the model:', error);
        alert('Could not load actor model. See console for details.');
      });
    };

    const addShape = (type: 'cube' | 'sphere') => {
      let geometry: THREE.BufferGeometry;
      if (type === 'cube') {
        geometry = new THREE.BoxGeometry(1, 1, 1);
      } else {
        geometry = new THREE.SphereGeometry(0.5, 32, 32);
      }
      const material = new THREE.MeshStandardMaterial({ color: Math.random() * 0xffffff });
      const mesh = new THREE.Mesh(geometry, material);
      mesh.castShadow = true;
      mesh.position.set((objects.length - 2) * 2, 0.5, 3);
      scene.add(mesh);
      objects.push(mesh);
    };
    
    // Add initial objects
    addActor();
    addShape('cube');

    // Event Listeners
    const onPointerClick = (event: MouseEvent) => {
      if ((event.target as HTMLElement)?.tagName === 'CANVAS' && transformControls.dragging) {
        return;
      }

      const rect = renderer.domElement.getBoundingClientRect();
      mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

      raycaster.setFromCamera(mouse, camera);
      const intersects = raycaster.intersectObjects(objects, true);

      if (intersects.length > 0) {
        const object = intersects[0].object;
        let parent = object;
        while(parent.parent && parent.parent !== scene) {
            parent = parent.parent;
        }
        transformControls.attach(parent);
      } else {
        transformControls.detach();
      }
    };
    
    renderer.domElement.addEventListener('click', onPointerClick);
    
    // Expose add functions to window for buttons
    (window as any).addActor = addActor;
    (window as any).addShape = addShape;
    (window as any).setTransformMode = (newMode: 'translate' | 'rotate' | 'scale') => {
        setMode(newMode);
        transformControls.setMode(newMode);
    };


    // Animation loop
    const animate = () => {
      requestAnimationFrame(animate);
      const delta = clock.getDelta();
      mixers.forEach(mixer => mixer.update(delta));
      orbitControls.update();
      renderer.render(scene, camera);
    };
    animate();

    // Handle window resize
    const handleResize = () => {
      camera.aspect = currentMount.clientWidth / currentMount.clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(currentMount.clientWidth, currentMount.clientHeight);
    };
    window.addEventListener('resize', handleResize);

    // Cleanup
    return () => {
      window.removeEventListener('resize', handleResize);
      renderer.domElement.removeEventListener('click', onPointerClick);
      currentMount.removeChild(renderer.domElement);
      transformControls.dispose();
      orbitControls.dispose();
      renderer.dispose();
      delete (window as any).addActor;
      delete (window as any).addShape;
      delete (window as any).setTransformMode;
    };
  }, [data, selectedShow, selectedSeries]); // Re-run on data/show/series change

  if (!data || showNames.length === 0) {
    return <p className="text-sm text-muted-foreground">Нет данных для отображения.</p>;
  }

  return (
    <div className="w-full">
      <div className="space-y-4">
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
                className={`whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm ${
                    name === selectedSeries
                    ? 'border-primary text-primary'
                    : 'border-transparent text-muted-foreground hover:text-foreground hover:border-gray-300'
                }`}
                >
                {name}
                </button>
            ))}
            </nav>
        </div>
      </div>
      <div className="space-y-4 mt-4">
        <div className="flex items-center justify-center gap-2 p-2 rounded-md bg-muted/50">
            <button onClick={() => (window as any).addActor()} className="px-3 py-1 text-sm font-semibold border rounded-full">Add Actor</button>
            <button onClick={() => (window as any).addShape('cube')} className="px-3 py-1 text-sm font-semibold border rounded-full">Add Cube</button>
            <button onClick={() => (window as any).addShape('sphere')} className="px-3 py-1 text-sm font-semibold border rounded-full">Add Sphere</button>
            <span className="w-px h-5 bg-border mx-2"></span>
            <button onClick={() => (window as any).setTransformMode('translate')} className={`px-3 py-1 text-sm font-semibold border rounded-l-full ${mode === 'translate' ? 'bg-primary text-primary-foreground' : ''}`}>Move</button>
            <button onClick={() => (window as any).setTransformMode('rotate')} className={`px-3 py-1 text-sm font-semibold border-t border-b ${mode === 'rotate' ? 'bg-primary text-primary-foreground' : ''}`}>Rotate</button>
            <button onClick={() => (window as any).setTransformMode('scale')} className={`px-3 py-1 text-sm font-semibold border rounded-r-full ${mode === 'scale' ? 'bg-primary text-primary-foreground' : ''}`}>Scale</button>
        </div>
        <div ref={mountRef} className="w-full h-[60vh] border rounded-lg overflow-hidden relative">
          {/* Three.js canvas will be appended here */}
        </div>
      </div>
    </div>
  );
};

export default CanvasDisplay;