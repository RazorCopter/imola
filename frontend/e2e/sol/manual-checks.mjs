import fs from 'node:fs/promises';
import ts from 'typescript';
import {chromium, expect} from '@playwright/test';
const source=ts.transpileModule(await fs.readFile('e2e/sol/fixtures.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
const {installFixtures}=await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const browser=await chromium.launch();const page=await browser.newPage({viewport:{width:1440,height:900}});const {writes,unhandled}=await installFixtures(page);const checks=[];
try {
 await page.goto('http://127.0.0.1:5176/revisione');const resize=page.getByRole('button',{name:'Ridimensiona colonna Progetto',exact:true});await resize.waitFor();await resize.focus();await page.keyboard.press('ArrowRight');await expect(resize.locator('..')).toHaveCSS('min-width','236px');await page.keyboard.press('Home');await expect(resize.locator('..')).toHaveCSS('min-width','220px');checks.push('Resizer: ArrowRight e Home');
 const box=await resize.boundingBox();await page.mouse.move(box.x+4,box.y+8);await page.mouse.down();await page.mouse.move(box.x+44,box.y+8);await page.mouse.up();await expect(resize.locator('..')).toHaveCSS('min-width','260px');checks.push('Resizer: trascinamento puntatore');
 await page.goto('http://127.0.0.1:5176/progetti');await page.getByTestId('edit-project-p1').click();const dialog=page.getByRole('dialog');await dialog.getByLabel('Titolo',{exact:true}).waitFor();for(let i=0;i<22;i++)await page.keyboard.press('Tab');expect(await dialog.evaluate(e=>e.contains(document.activeElement))).toBeTruthy();await page.keyboard.press('Escape');await expect(page.getByTestId('edit-project-p1')).toBeFocused();checks.push('Dialog: focus trap con 22 Tab, Escape e ritorno');
 await page.emulateMedia({reducedMotion:'reduce'});await page.keyboard.press('Control+k');await page.getByRole('dialog').waitFor();const duration=await page.getByRole('dialog').evaluate(e=>getComputedStyle(e).animationDuration);expect(parseFloat(duration)*1000).toBeLessThanOrEqual(0.02);checks.push('Reduced motion: animazione dialog <= 0.02 ms');
 expect(writes).toHaveLength(0);expect(unhandled).toHaveLength(0);
 await fs.writeFile('../outputs/visual-review/sol-final/manual-interaction-checks.json',JSON.stringify({date:new Date().toISOString(),passed:checks.length,checks,writes,unhandled},null,2));console.log(JSON.stringify({passed:checks.length,checks}));
} finally {await browser.close();}
