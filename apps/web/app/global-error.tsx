"use client";
export default function GlobalError({reset}:{error:Error&{digest?:string};reset:()=>void}){
 return <html><body><main style={{maxWidth:640,margin:"15vh auto",padding:32,fontFamily:"sans-serif"}}><p>GENUINEGIGS / APPLICATION RECOVERY</p><h1>The application shell needs to reconnect.</h1><p>Your submitted operational work may already be saved. Reconnecting will reload authoritative state rather than submitting it again.</p><button onClick={()=>window.location.reload()}>Reconnect</button><button onClick={reset}>Try without reload</button></main></body></html>;
}
