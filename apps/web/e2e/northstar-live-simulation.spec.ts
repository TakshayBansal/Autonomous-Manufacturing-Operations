import { expect,test,type Page } from "@playwright/test";

const password="Northstar@2026";
const personas=[
 ["ananya.deshmukh@northstar-mobility.local","corporate"],
 ["vikram.kulkarni@northstar-mobility.local","plant_manager"],
 ["meera.jadhav@northstar-mobility.local","production_manager"],
 ["rohit.shinde@northstar-mobility.local","supervisor"],
 ["kavita.pawar@northstar-mobility.local","operator"],
 ["suresh.more@northstar-mobility.local","maintenance"],
 ["imran.shaikh@northstar-mobility.local","maintenance"],
 ["neha.bhosale@northstar-mobility.local","quality"],
 ["pooja.salunkhe@northstar-mobility.local","quality"],
 ["aditya.joshi@northstar-mobility.local","purchase"],
 ["snehal.patil@northstar-mobility.local","purchase"],
 ["nitin.gaikwad@northstar-mobility.local","stores"],
 ["mahesh.chavan@northstar-mobility.local","gate"],
 ["rhea.nair@northstar-mobility.local","admin"],
] as const;

async function login(page:Page,email:string){
 await page.context().clearCookies();
 const response=await page.request.post("http://127.0.0.1:8000/auth/login",{data:{email,password}});
 expect(response.status(),await response.text()).toBe(200);
 return (await response.json()).csrf_token as string;
}

test("every Northstar persona receives a distinct backend projection",async({page})=>{
 for(const [email,kind] of personas){
  await login(page,email);
  const response=await page.request.get("http://127.0.0.1:8000/api/v2/home");
  expect(response.status(),`${email}: ${await response.text()}`).toBe(200);
  const home=await response.json();
  expect(home.kind).toBe(kind);
  expect(home.simulation).toBe(true);
  if(!["plant_manager","purchase","corporate","admin"].includes(kind)){
   expect(JSON.stringify(home)).not.toContain("annualized_value");
   expect(JSON.stringify(home)).not.toContain("financial_impact\":");
  }
 }
});

test("operator and supervisor line scopes are enforced by the API",async({page})=>{
 await login(page,"kavita.pawar@northstar-mobility.local");
 expect((await page.request.get("http://127.0.0.1:8000/api/v2/lines/line-ns-01/workspace")).status()).toBe(200);
 expect((await page.request.get("http://127.0.0.1:8000/api/v2/lines/line-ns-02/workspace")).status()).toBe(403);
 await login(page,"rohit.shinde@northstar-mobility.local");
 expect((await page.request.get("http://127.0.0.1:8000/api/v2/lines/line-ns-02/workspace")).status()).toBe(200);
 expect((await page.request.get("http://127.0.0.1:8000/api/v2/lines/line-ns-03/workspace")).status()).toBe(403);
});

test("machine failure becomes maintenance work and a visible deviation",async({page})=>{
 const csrf=await login(page,"rhea.nair@northstar-mobility.local");
 const injected=await page.request.post("http://127.0.0.1:8000/api/v2/simulation/scenarios/spindle_temperature_failure",{headers:{"x-csrf-token":csrf,"Idempotency-Key":crypto.randomUUID()},data:{}});
 expect(injected.status(),await injected.text()).toBe(200);
 await expect.poll(async()=>{
  const response=await page.request.get("http://127.0.0.1:8000/api/v2/deviations");
  const rows=await response.json();
  return rows.some((row:{detector_key:string})=>row.detector_key==="downtime_exceeded_threshold");
 },{timeout:5000}).toBe(true);
 await page.goto("/operations/admin");
 await expect(page.getByRole("heading",{name:"Live factory control room"})).toBeVisible();
 await expect(page.getByRole("button",{name:/Spindle temperature failure/})).toBeVisible();
});

test("supplier email, customer demand and gate mismatch become canonical work",async({page})=>{
 const csrf=await login(page,"rhea.nair@northstar-mobility.local");
 for(const scenario of ["supplier_email_change","customer_order_surge","inbound_vehicle_mismatch"]){
  const response=await page.request.post(`http://127.0.0.1:8000/api/v2/simulation/scenarios/${scenario}`,{headers:{"x-csrf-token":csrf,"Idempotency-Key":crypto.randomUUID()},data:{}});
  expect(response.status(),await response.text()).toBe(200);
 }
 await login(page,"mahesh.chavan@northstar-mobility.local");
 const gate=await (await page.request.get("http://127.0.0.1:8000/api/v2/home")).json();
 expect(gate.expected_arrivals.some((row:{title:string})=>row.title.includes("challan quantity mismatch"))).toBe(true);
 await login(page,"snehal.patil@northstar-mobility.local");
 const purchase=await (await page.request.get("http://127.0.0.1:8000/api/v2/home")).json();
 expect(purchase.supplier_updates.some((row:{title:string})=>row.title.includes("Delivery commitment revision"))).toBe(true);
});
