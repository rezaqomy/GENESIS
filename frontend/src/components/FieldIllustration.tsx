// A small composition of the project's existing, locally served game artwork.
export function FieldIllustration({compact=false}:{compact?:boolean}) {
  return <div className={`field-illustration${compact?' compact':''}`} aria-hidden="true">
    <span className="field-orbit"/><span className="field-ground"/>
    <img className="field-tree back" src="/assets/genesis/pine.png" alt=""/>
    <img className="field-home" src="/assets/genesis/shelter.png" alt=""/>
    <img className="field-tree front" src="/assets/genesis/oak.png" alt=""/>
    <img className="field-fire" src="/assets/genesis/campfire.png" alt=""/>
    <img className="field-bush" src="/assets/genesis/berry_bush.png" alt=""/>
  </div>
}
