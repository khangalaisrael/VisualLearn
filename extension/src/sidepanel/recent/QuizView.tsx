/**
 * Taking a quiz: one question at a time, marked the moment an option is
 * picked (the quiz carries its own answers, so marking needs no request),
 * with the short explanation and a tutor on hand for more. A finished run of
 * the whole quiz is recorded so the series can show the best score; a second
 * pass over only the missed questions is practice and is not recorded.
 */

import { useState } from "react";

import type { QuizOut } from "@shared/types";

import { recordQuizAttempt } from "../../shared/api-client";
import { Button } from "../components/Button";
import { MathText } from "../components/MathText";
import { BackIcon } from "./parts";
import { TutorChat } from "./TutorChat";

const RIGHT = "border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-200";
const WRONG = "border-red-200 bg-red-50 text-red-800 dark:text-red-200";

function letter(index: number): string {
  return String.fromCharCode(65 + index);
}

export function QuizView({ quiz, onBack }: { quiz: QuizOut; onBack: () => void }): JSX.Element {
  // Per question of the quiz: undefined = not answered yet; null = skipped.
  const [answers, setAnswers] = useState<(number | null | undefined)[]>(() => quiz.questions.map(() => undefined));
  // The questions of this run, as indexes into the quiz: all of them, or the missed ones on a second pass.
  const [order, setOrder] = useState<number[]>(() => quiz.questions.map((_, i) => i));
  const [position, setPosition] = useState(0);
  const [finished, setFinished] = useState(false);
  const [tutorOpen, setTutorOpen] = useState(false);
  const [reviewing, setReviewing] = useState<number | null>(null);

  const total = order.length;
  const wholeQuiz = total === quiz.questions.length;
  const isRight = (q: number) => answers[q] === quiz.questions[q].correct_index;
  const score = order.filter(isRight).length;
  const missed = order.filter((q) => !isRight(q));

  const goNext = () => {
    setTutorOpen(false);
    if (position + 1 < total) {
      setPosition(position + 1);
      return;
    }
    setFinished(true);
    if (wholeQuiz) {
      // Best effort: the student already has their result on screen.
      void recordQuizAttempt(quiz.id, answers.map((answer) => answer ?? null)).catch(() => undefined);
    }
  };

  const start = (questions: number[]) => {
    setAnswers((prev) => prev.map((answer, q) => (questions.includes(q) ? undefined : answer)));
    setOrder(questions);
    setPosition(0);
    setFinished(false);
    setTutorOpen(false);
    setReviewing(null);
  };

  const back = (
    <button
      type="button"
      onClick={onBack}
      className="-ml-1 flex items-center gap-1 self-start rounded-sm px-1 py-1 text-sm font-medium text-slate-500 transition-colors duration-[120ms] hover:bg-slate-50 hover:text-slate-700"
    >
      <BackIcon />
      Back to the series
    </button>
  );

  if (finished) {
    return (
      <div className="flex flex-col gap-4">
        {back}
        <div className="flex flex-col gap-1">
          <p className="text-xs font-medium text-slate-500">{quiz.title}</p>
          <h2 className="text-lg font-semibold tabular-nums text-slate-800">
            {score} of {total} correct
          </h2>
          <p className="text-sm text-slate-500">
            {missed.length > 0
              ? "Open any question below to see why, then go again on the ones you missed."
              : wholeQuiz
                ? "Every one right. A new quiz will test other parts of the series."
                : "All of them right this time."}
          </p>
        </div>

        <ul className="flex flex-col gap-2">
          {order.map((q) => {
            const question = quiz.questions[q];
            const chosen = answers[q];
            const right = isRight(q);
            const open = reviewing === q;
            return (
              <li key={q} className="rounded-md border border-slate-200">
                <button
                  type="button"
                  aria-expanded={open}
                  onClick={() => setReviewing(open ? null : q)}
                  className="flex w-full items-start gap-3 rounded-md p-3 text-left transition-colors duration-[120ms] hover:bg-slate-50"
                >
                  <span
                    className={`mt-0.5 flex-none rounded-full border px-2 py-0.5 text-[11px] font-medium ${right ? RIGHT : WRONG}`}
                  >
                    {right ? "Right" : chosen == null ? "Skipped" : "Wrong"}
                  </span>
                  <span className="min-w-0 flex-1 text-sm text-slate-700">
                    <MathText text={question.question} />
                  </span>
                </button>
                {open && (
                  <div className="flex flex-col gap-2 border-t border-slate-100 p-3 text-sm text-slate-700">
                    {chosen != null && !right && (
                      <p>
                        <span className="font-medium">You chose {letter(chosen)}.</span>{" "}
                        <MathText text={question.options[chosen]} />
                      </p>
                    )}
                    <p>
                      <span className="font-medium">Answer: {letter(question.correct_index)}.</span>{" "}
                      <MathText text={question.options[question.correct_index]} />
                    </p>
                    <div className="text-slate-600">
                      <MathText text={question.explanation} />
                    </div>
                  </div>
                )}
              </li>
            );
          })}
        </ul>

        {quiz.resources.length > 0 && (
          <section className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold text-slate-800">To study further</h3>
            <ul className="flex flex-col gap-2">
              {quiz.resources.map((resource) => (
                <li key={resource.url} className="rounded-md border border-slate-200 p-3">
                  <a
                    href={resource.url}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="text-sm font-medium text-indigo-600 underline-offset-2 hover:underline dark:text-indigo-300"
                  >
                    {resource.title}
                  </a>
                  <p className="mt-1 text-xs text-slate-500">{resource.why}</p>
                  <p className="mt-1 truncate text-xs text-slate-400">{new URL(resource.url).hostname}</p>
                </li>
              ))}
            </ul>
          </section>
        )}

        <div className="flex flex-wrap gap-2">
          {missed.length > 0 && (
            <Button onClick={() => start(missed)}>
              {missed.length === 1 ? "Retry the one you missed" : `Retry the ${missed.length} you missed`}
            </Button>
          )}
          <Button variant={missed.length > 0 ? "secondary" : "primary"} onClick={() => start(quiz.questions.map((_, i) => i))}>
            {missed.length > 0 ? "Whole quiz again" : "Try again"}
          </Button>
          <Button variant="secondary" onClick={onBack}>
            Done
          </Button>
        </div>
      </div>
    );
  }

  const q = order[position];
  const question = quiz.questions[q];
  const chosen = answers[q];
  const answered = chosen !== undefined;
  const correct = chosen === question.correct_index;

  const choose = (option: number | null) => {
    if (answered) return;
    setAnswers((prev) => prev.map((answer, i) => (i === q ? option : answer)));
  };

  return (
    <div className="flex flex-col gap-4">
      {back}
      <div className="flex flex-col gap-2">
        <p className="text-xs font-medium tabular-nums text-slate-500">
          Question {position + 1} of {total}
        </p>
        {/* Position in the run: one segment per question. */}
        <div className="flex gap-1" aria-hidden="true">
          {order.map((id, i) => (
            <span key={id} className={`h-1 flex-1 rounded-full ${i <= position ? "bg-indigo-600" : "bg-slate-200"}`} />
          ))}
        </div>
      </div>

      <div className="text-base font-medium leading-relaxed text-slate-800">
        <MathText text={question.question} />
      </div>

      <ul className="flex flex-col gap-2">
        {question.options.map((option, i) => {
          const isCorrect = i === question.correct_index;
          const state = !answered
            ? "border-slate-200 bg-white text-slate-700 hover:border-indigo-200 hover:bg-indigo-50/40 active:bg-indigo-50"
            : isCorrect
              ? RIGHT
              : i === chosen
                ? WRONG
                : "border-slate-200 text-slate-400";
          return (
            <li key={i}>
              <button
                type="button"
                disabled={answered}
                onClick={() => choose(i)}
                className={`flex w-full items-start gap-3 rounded-md border p-3 text-left text-sm transition-colors duration-[120ms] ${state}`}
              >
                <span className="flex-none font-semibold">{letter(i)}</span>
                <span className="min-w-0 flex-1">
                  <MathText text={option} />
                </span>
                {answered && (isCorrect || i === chosen) && (
                  <span className="flex-none text-xs font-medium">{isCorrect ? "Correct" : "Your answer"}</span>
                )}
              </button>
            </li>
          );
        })}
      </ul>

      {!answered && (
        <button
          type="button"
          onClick={() => choose(null)}
          className="self-start rounded-sm px-2 py-1 text-xs font-medium text-slate-500 transition-colors duration-[120ms] hover:bg-slate-100 hover:text-slate-700"
        >
          I don't know, show me
        </button>
      )}

      {answered && (
        <div className="flex flex-col gap-3" role="status">
          <div className="rounded-md bg-slate-50 p-3 text-sm leading-relaxed text-slate-700">
            <p className="mb-1 font-semibold text-slate-800">
              {correct
                ? "Correct."
                : chosen === null
                  ? `The answer is ${letter(question.correct_index)}.`
                  : `Not quite. The answer is ${letter(question.correct_index)}.`}
            </p>
            <MathText text={question.explanation} />
          </div>
          <div className="flex flex-wrap gap-2">
            <Button onClick={goNext}>{position + 1 < total ? "Next question" : "See results"}</Button>
            {!tutorOpen && (
              <Button variant="secondary" onClick={() => setTutorOpen(true)}>
                {correct ? "Go deeper" : "Explain it to me"}
              </Button>
            )}
          </div>
          {tutorOpen && (
            <TutorChat
              key={q}
              quizId={quiz.id}
              seriesId={quiz.series_id}
              questionIndex={q}
              questionText={question.question}
              selectedIndex={chosen ?? null}
              correct={correct}
            />
          )}
        </div>
      )}
    </div>
  );
}
