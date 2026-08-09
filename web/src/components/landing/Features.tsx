import { DailyPnLCalendar } from "@/components/shared/DailyPnLCalendar";
import type { DailyPnL } from "@/lib/signals";

const FEATURES = [
  {
    title: "ស្កេនបច្ចេកទេស",
    body: "ការឆ្លង EMA 9/21 ចម្រោះដោយ RSI និង MACD លើទៀន 1 ម៉ោង — ការរៀបចំរកឃើញដោយច្បាប់ មិនមែនដោយអារម្មណ៍។",
  },
  {
    title: "ការបញ្ជាក់ដោយ AI",
    body: "បេក្ខភាពគ្រប់មួយត្រូវបានពិនិត្យដោយ SEA-LION មុននឹងក្លាយជា signal។ គ្មានការបញ្ជាក់ គ្មាន signal។",
  },
  {
    title: "បរិបទព័ត៌មាន",
    body: "ចំណងជើងថ្មីៗត្រូវបានអានរួមជាមួយតារាង ដូច្នេះការរៀបចំស្អាតអាចត្រូវបានបដិសេធ នៅពេលព័ត៌មាននិយាយផ្ទុយ។",
  },
  {
    title: "កំណត់ហានិភ័យជាមុន",
    body: "បញ្ឈប់ខាតហួសចំណុចប្រែប្រួលថ្មីៗ ជាមួយសតិបណ្ដោះអាសន្ន ATR ។ គោលដៅនៅសមាមាត្ររង្វាន់ទៅហានិភ័យ 2:1។ ជានិច្ច។",
  },
  {
    title: "តាមដានលទ្ធផល",
    body: "Open signals ត្រូវបានតាមដានរាល់ដំណើរការ។ នៅពេលតម្លៃឈានដល់ TP ឬ SL ស្ថានភាពធ្វើបច្ចុប្បន្នភាពដោយស្វ័យប្រវត្តិ។",
  },
  {
    title: "វិន័យបិទនៅពេលបរាជ័យ",
    body: "ប្រសិនបើ AI ខុស ឬឆ្លើយមិនច្បាស់ ការរៀបចំត្រូវបានបោះបង់។ Signals ដែលមិនបានបញ្ជាក់មិនដែលត្រូវបានផ្សាយទេ។",
  },
];

export function Features({ dailyPnL }: { dailyPnL: DailyPnL[] }) {
  return (
    <section
      id="features"
      className="flex min-h-[calc(100dvh-4rem)] items-center border-b border-line bg-card"
    >
      <div className="mx-auto grid w-full max-w-[100rem] gap-10 px-6 py-10 md:py-14 lg:grid-cols-[0.6fr_1.4fr] lg:items-center lg:gap-16 xl:px-10">
        <div>
          <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-ink">
            របៀបដំណើរការ
          </p>
          <h2 className="mt-1 text-xl font-bold tracking-tight text-ink md:text-2xl">
            A signal គឺជាបញ្ជីពិនិត្យ មិនមែនការទាយ។
          </h2>

          <ul className="mt-6 flex flex-col gap-4">
            {FEATURES.map((f) => (
              <li key={f.title} className="flex gap-3">
                <span
                  className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-long-soft text-[11px] font-bold text-long"
                  aria-hidden
                >
                  ✓
                </span>
                <div>
                  <h3 className="text-sm font-semibold text-ink">{f.title}</h3>
                  <p className="mt-0.5 text-[13px] leading-relaxed text-slate">
                    {f.body}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <div>
          <DailyPnLCalendar
            data={dailyPnL}
            description={null}
            interactive={false}
            compact
          />
        </div>
      </div>
    </section>
  );
}
